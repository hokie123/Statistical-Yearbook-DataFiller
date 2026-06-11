import asyncio
import random
from urllib.parse import quote_plus

import pandas as pd

from .config import AppConfig
from .constants import CODE_COL, VALUE_COL
from .evidence import (
    build_queries,
    build_record_update,
    choose_primary_query,
    ensure_columns,
    is_missing,
)
from .llm import classify_with_optional_llm
from .scraping import (
    CaptchaBlockedError,
    SearchRequestError,
    create_persistent_context,
    recover_from_captcha_block,
    search_google_with_context,
)

REQUEST_PROXY_PORT_COL = "request_proxy_port"
CAPTCHA_RECOVERED_FLAG = "__captcha_recovered"


def ensure_runtime_columns(df: pd.DataFrame) -> pd.DataFrame:
    if REQUEST_PROXY_PORT_COL not in df.columns:
        df[REQUEST_PROXY_PORT_COL] = ""
    if CAPTCHA_RECOVERED_FLAG not in df.columns:
        df[CAPTCHA_RECOVERED_FLAG] = ""
    return df


def choose_proxy_port(proxy_ports: list[int]) -> int | None:
    if not proxy_ports:
        return None
    return random.choice(proxy_ports)


def apply_prepare_only_updates(df: pd.DataFrame, target_indices: list[int]) -> pd.DataFrame:
    for idx in target_indices:
        row = df.loc[idx]
        df.at[idx, "search_query"] = choose_primary_query(row)
        df.at[idx, "search_url"] = f"https://www.google.com/search?q={quote_plus(df.at[idx, 'search_query'])}"
        df.at[idx, "fetch_status"] = "prepared_only"
        df.at[idx, "llm_status"] = "disabled"
        df.at[idx, "manual_review_status"] = "pending"
        df.at[idx, "need_manual_check"] = "yes"
        df.at[idx, REQUEST_PROXY_PORT_COL] = ""
    return df


async def run_collection(config: AppConfig) -> None:
    # ---------- Special mode: resolve CAPTCHA only ----------
    if config.resolve_captcha:
        from playwright.async_api import async_playwright
        from .scraping import resolve_captcha_interactive

        async with async_playwright() as playwright:
            proxy_port = choose_proxy_port(config.proxy_ports)
            await resolve_captcha_interactive(
                playwright,
                config.user_data_dir,
                proxy_port=proxy_port,
            )
        return

    # ---------- Normal evidence collection ----------
    df = pd.read_csv(config.input_path, dtype={CODE_COL: str})
    df = ensure_columns(df)
    df = ensure_runtime_columns(df)

    if VALUE_COL not in df.columns:
        raise KeyError(f"Missing required target column: {VALUE_COL}")

    target_indices = [idx for idx in df.index if is_missing(df.at[idx, VALUE_COL])]
    if config.max_rows is not None:
        target_indices = target_indices[: config.max_rows]

    print(f"Rows requiring evidence collection: {len(target_indices)}")

    if config.prepare_only:
        df = apply_prepare_only_updates(df, target_indices)
        df.to_csv(config.output_path, index=False, encoding="utf-8-sig")
        print(f"Prepared review sheet written to: {config.output_path}")
        return

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        # Create persistent browser context (saves session across queries)
        captcha_was_resolved = False
        context = await create_persistent_context(
            playwright=playwright,
            user_data_dir=config.user_data_dir,
            headless=config.headless,
            proxy_port=choose_proxy_port(config.proxy_ports),
        )

        try:
            for counter, idx in enumerate(target_indices, start=1):
                row = df.loc[idx]
                queries = build_queries(row)
                print(f"[{counter}/{len(target_indices)}] {queries[0]}")

                last_error = ""
                row_succeeded = False
                for query in queries:
                    for attempt in range(config.retry_attempts + 1):
                        proxy_port = choose_proxy_port(config.proxy_ports)
                        try:
                            page_text, results, final_url = await search_google_with_context(
                                context=context,
                                query=query,
                            )
                            primary_result = results[0] if results else {"title": "", "url": final_url}
                            update = build_record_update(
                                row=row,
                                query=query,
                                page_text=page_text,
                                source_title=primary_result["title"],
                                source_url=primary_result["url"],
                            )
                            update[REQUEST_PROXY_PORT_COL] = proxy_port or ""
                            update = classify_with_optional_llm(
                                row=row,
                                page_text=page_text,
                                source_title=primary_result["title"],
                                source_url=primary_result["url"],
                                base_update=update,
                                config=config,
                            )
                            for key, value in update.items():
                                df.at[idx, key] = value
                            row_succeeded = True
                            break

                        except CaptchaBlockedError as exc:
                            last_error = str(exc)
                            df.at[idx, REQUEST_PROXY_PORT_COL] = proxy_port or ""

                            if captcha_was_resolved:
                                print("  CAPTCHA blocked again — reopening recovery browser...")

                            await context.close()
                            context = await recover_from_captcha_block(
                                playwright=playwright,
                                user_data_dir=config.user_data_dir,
                                block_url=exc.block_url,
                                proxy_port=proxy_port,
                            )
                            captcha_was_resolved = True
                            df.at[idx, CAPTCHA_RECOVERED_FLAG] = "resolved"
                            continue

                        except SearchRequestError as exc:
                            last_error = str(exc)
                            df.at[idx, "search_query"] = query
                            df.at[idx, "search_url"] = f"https://www.google.com/search?q={quote_plus(query)}"
                            df.at[idx, "fetch_status"] = f"failed: {last_error}"
                            df.at[idx, REQUEST_PROXY_PORT_COL] = proxy_port or ""
                            if exc.retryable and attempt < config.retry_attempts:
                                retry_delay = random.uniform(config.retry_delay_min, config.retry_delay_max)
                                print(
                                    f"  retrying query after {retry_delay:.1f}s "
                                    f"(attempt {attempt + 1}/{config.retry_attempts}, port={proxy_port or 'direct'})"
                                )
                                await asyncio.sleep(retry_delay)
                                continue
                            break

                        except Exception as exc:
                            last_error = repr(exc)
                            df.at[idx, "search_query"] = query
                            df.at[idx, "search_url"] = f"https://www.google.com/search?q={quote_plus(query)}"
                            df.at[idx, "fetch_status"] = f"failed: {last_error}"
                            df.at[idx, REQUEST_PROXY_PORT_COL] = proxy_port or ""
                            break

                    if row_succeeded:
                        break

                if not row_succeeded:
                    df.at[idx, "manual_review_status"] = "pending"
                    df.at[idx, "need_manual_check"] = "yes"
                    df.at[idx, "review_notes"] = last_error

                df.to_csv(config.output_path, index=False, encoding="utf-8-sig")
                await asyncio.sleep(random.uniform(config.sleep_min, config.sleep_max))

        finally:
            await context.close()

    df.to_csv(config.output_path, index=False, encoding="utf-8-sig")
    print(f"Evidence review output written to: {config.output_path}")
