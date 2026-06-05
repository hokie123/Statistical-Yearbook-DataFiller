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
from .scraping import create_context, search_google


def apply_prepare_only_updates(df: pd.DataFrame, target_indices: list[int]) -> pd.DataFrame:
    for idx in target_indices:
        row = df.loc[idx]
        df.at[idx, "search_query"] = choose_primary_query(row)
        df.at[idx, "search_url"] = f"https://www.google.com/search?q={quote_plus(df.at[idx, 'search_query'])}"
        df.at[idx, "fetch_status"] = "prepared_only"
        df.at[idx, "llm_status"] = "disabled"
        df.at[idx, "manual_review_status"] = "pending"
        df.at[idx, "need_manual_check"] = "yes"
    return df


async def run_collection(config: AppConfig) -> None:
    df = pd.read_csv(config.input_path, dtype={CODE_COL: str})
    df = ensure_columns(df)

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
        context = await create_context(playwright, config.headless)
        page = await context.new_page()

        for counter, idx in enumerate(target_indices, start=1):
            row = df.loc[idx]
            queries = build_queries(row)
            print(f"[{counter}/{len(target_indices)}] {queries[0]}")

            last_error = ""
            for query in queries:
                try:
                    page_text, results = await search_google(page, query)
                    primary_result = results[0] if results else {"title": "", "url": page.url}
                    update = build_record_update(
                        row=row,
                        query=query,
                        page_text=page_text,
                        source_title=primary_result["title"],
                        source_url=primary_result["url"],
                    )
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
                    break
                except Exception as exc:
                    last_error = repr(exc)
                    df.at[idx, "search_query"] = query
                    df.at[idx, "search_url"] = f"https://www.google.com/search?q={quote_plus(query)}"
                    df.at[idx, "fetch_status"] = f"failed: {last_error}"
            else:
                df.at[idx, "manual_review_status"] = "pending"
                df.at[idx, "need_manual_check"] = "yes"
                df.at[idx, "review_notes"] = last_error

            df.to_csv(config.output_path, index=False, encoding="utf-8-sig")
            sleep_ms = int(random.uniform(config.sleep_min, config.sleep_max) * 1000)
            await page.wait_for_timeout(sleep_ms)

        await context.close()

    df.to_csv(config.output_path, index=False, encoding="utf-8-sig")
    print(f"Evidence review output written to: {config.output_path}")
