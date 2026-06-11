import asyncio
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .constants import DEFAULT_USER_AGENT

USER_AGENTS = [
    DEFAULT_USER_AGENT,
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) "
        "Gecko/20100101 Firefox/137.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:137.0) "
        "Gecko/20100101 Firefox/137.0"
    ),
]

RETRYABLE_ERROR_MARKERS = (
    "net::err_",
    "connection reset",
    "connection refused",
    "connection timed out",
    "timed out",
    "temporarily unavailable",
    "proxy",
)

# CAPTCHA detection markers — Google anti-bot page fingerprints
CAPTCHA_MARKERS = (
    "/sorry/index",
    "unusual traffic",
    "我们的系统检测到您的计算机网络中存在异常流量",
    "automated queries",
)


@dataclass
class SearchSessionResult:
    page_text: str
    results: list[dict[str, str]]
    final_url: str
    user_agent: str
    proxy_port: int | None


class SearchRequestError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class CaptchaBlockedError(RuntimeError):
    """Raised when Google returns a CAPTCHA/block page."""

    def __init__(self, block_url: str) -> None:
        super().__init__(f"Blocked by Google CAPTCHA: {block_url}")
        self.block_url = block_url


def choose_user_agent() -> str:
    return random.choice(USER_AGENTS)


def _is_retryable_error_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in RETRYABLE_ERROR_MARKERS)


def _get_playwright_timeout_error() -> type[Exception]:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    return PlaywrightTimeoutError


def is_captcha_page(page_url: str, page_text: str = "") -> bool:
    """Detect whether the current page is a Google CAPTCHA/block page."""
    lowered_url = page_url.lower()
    for marker in CAPTCHA_MARKERS:
        if marker in lowered_url:
            return True
    if page_text:
        lowered_text = page_text.lower()
        for marker in CAPTCHA_MARKERS:
            if marker in lowered_text:
                return True
    return False


async def apply_stealth_to_page(page: Any) -> None:
    """Apply playwright-stealth evasions to a page."""
    from playwright_stealth import Stealth

    stealth = Stealth(
        chrome_app=True,
        chrome_csi=True,
        chrome_load_times=True,
        chrome_runtime=False,
        hairline=True,
        iframe_content_window=True,
        media_codecs=True,
        navigator_hardware_concurrency=True,
        navigator_languages=True,
        navigator_permissions=True,
        navigator_platform=True,
        navigator_plugins=True,
        navigator_user_agent=True,
        navigator_user_agent_data=True,
        navigator_vendor=True,
        navigator_webdriver=True,
        error_prototype=True,
        sec_ch_ua=True,
        webgl_vendor=True,
    )
    await stealth.apply_stealth_async(page)


async def create_persistent_context(
    playwright: Any,
    user_data_dir: str,
    headless: bool,
    proxy_port: int | None,
) -> Any:
    """
    Create a persistent browser context that saves cookies/session across runs.

    This is the key to bypassing Google CAPTCHA: solve it once in headed mode,
    and the session cookie is persisted in ``user_data_dir`` for all future runs.
    """
    user_agent = choose_user_agent()
    launch_options: dict[str, Any] = {
        "headless": headless,
        "slow_mo": 120,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
        ],
    }
    if proxy_port is not None:
        launch_options["proxy"] = {"server": f"http://127.0.0.1:{proxy_port}"}

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        **launch_options,
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
        user_agent=user_agent,
    )
    return context


async def resolve_captcha_interactive(playwright: Any, user_data_dir: str, proxy_port: int | None = None) -> None:
    """
    Interactive CAPTCHA resolver tool.

    Opens Google in headed (visible) mode so the user can manually
    complete the CAPTCHA. The session is saved to ``user_data_dir``
    for reuse in subsequent headless runs.
    """
    print(
        "\n========================================"
        "\n  Google CAPTCHA Resolver"
        "\n========================================"
        "\nOpening browser..."
        "\nPlease:"
        "\n  1. Complete the Google verification prompt"
        "\n  2. After verification, close the browser window"
        "\n(The session will be saved for future reuse)"
        "\n========================================"
    )

    launch_kwargs: dict[str, Any] = {
        "headless": False,
        "slow_mo": 50,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
        ],
    }
    if proxy_port is not None:
        launch_kwargs["proxy"] = {"server": f"http://127.0.0.1:{proxy_port}"}

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        **launch_kwargs,
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
    )

    page = await context.new_page()

    # Apply stealth evasions
    try:
        await apply_stealth_to_page(page)
    except Exception:
        pass

    # Open Google to trigger CAPTCHA
    await page.goto("https://www.google.com/search?q=test", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)

    # If already redirected to the CAPTCHA page, notify the user
    if is_captcha_page(page.url):
        print("  CAPTCHA page loaded. Please complete the verification in the browser...")
    else:
        print("  Google homepage loaded. You can search to trigger verification, or close the browser.")

    # Poll until the CAPTCHA is resolved (URL is no longer on the /sorry/ page)
    print("  Waiting for verification to complete (auto-detects CAPTCHA clearance)...")
    for _ in range(300):  # Max 5 minutes
        await asyncio.sleep(1)
        try:
            current_url = page.url
            if not is_captcha_page(current_url) and "google.com/search" in current_url:
                print("\n  ✅ CAPTCHA cleared! Session saved.")
                break
        except Exception:
            break
    else:
        print("\n  Polling timed out, but the session may have been saved.")

    await page.close()
    await context.close()
    print("  Browser closed. You can now run with --headless.\n")


async def recover_from_captcha_block(
    playwright: Any,
    user_data_dir: str,
    block_url: str,
    proxy_port: int | None,
) -> Any:
    """
    When Google blocks us with a CAPTCHA, reopen the browser in headed mode
    so the user can manually solve it. Once solved, return a fresh persistent
    context (now with a trusted session cookie saved to user_data_dir).
    """
    print(
        "\n========================================"
        "\n  Google CAPTCHA Detected!"
        "\n========================================"
        "\nOpening browser in visible mode for you to complete verification."
        "\nThe page will redirect automatically after approval."
        "\n========================================"
    )

    recovery_context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        slow_mo=50,
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
        ],
    )
    if proxy_port is not None:
        await recovery_context.close()
        print(f"  Note: proxy port {proxy_port} not applied during CAPTCHA recovery (use direct connection)")
        recovery_context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            slow_mo=50,
            locale="zh-CN",
            viewport={"width": 1366, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
            ],
        )

    page = await recovery_context.new_page()
    await page.goto(block_url, wait_until="domcontentloaded", timeout=60000)

    # Poll until CAPTCHA is resolved
    print("  Waiting for verification (auto-detection, up to 5 minutes)...")
    for _ in range(300):
        await asyncio.sleep(1)
        try:
            current_url = page.url
            if not is_captcha_page(current_url) and ("google.com/search" in current_url or "google.com/webhp" in current_url):
                print("  ✅ CAPTCHA cleared! Resuming execution.")
                break
        except Exception:
            await asyncio.sleep(1)
            continue
    else:
        print("  ⚠️ Polling timed out. Continuing (session may have been saved).")

    await page.close()
    print("  CAPTCHA resolved! Session saved to browser profile.\n")

    return recovery_context


async def search_google_with_context(
    context: Any,
    query: str,
) -> tuple[str, list[dict[str, str]], str]:
    """
    Perform a Google search using an existing persistent context.
    Applies stealth and returns (page_text, results, final_url).
    """
    timeout_error = _get_playwright_timeout_error()
    page = await context.new_page()

    # Apply stealth evasion to each new page
    try:
        await apply_stealth_to_page(page)
    except Exception:
        pass  # Stealth is non-critical; continue if it fails

    search_url = "https://www.google.com/search?q=" + quote_plus(query)
    try:
        response = await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    except timeout_error as exc:
        await page.close()
        raise SearchRequestError(f"request timeout for query: {query}", retryable=True) from exc
    except Exception as exc:
        await page.close()
        message = str(exc) or repr(exc)
        raise SearchRequestError(message, retryable=_is_retryable_error_message(message)) from exc

    status_code = response.status if response is not None else None
    final_url = page.url

    # Detect CAPTCHA page
    if is_captcha_page(final_url):
        await page.close()
        raise CaptchaBlockedError(block_url=final_url)

    if status_code == 429 or (status_code is not None and status_code >= 500):
        await page.close()
        raise SearchRequestError(
            f"temporary HTTP {status_code} for query: {query}",
            retryable=True,
            status_code=status_code,
        )

    await page.wait_for_timeout(4000)
    try:
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(1500)
    except Exception:
        pass

    try:
        page_text = await page.locator("body").inner_text(timeout=20000)
    except timeout_error as exc:
        await page.close()
        raise SearchRequestError(f"page text timeout for query: {query}", retryable=True) from exc
    except Exception as exc:
        await page.close()
        message = str(exc) or repr(exc)
        raise SearchRequestError(message, retryable=_is_retryable_error_message(message)) from exc

    results = await extract_search_results(page)
    await page.close()
    return page_text, results, final_url


async def create_context(
    playwright: Any,
    headless: bool,
    user_agent: str,
    proxy_port: int | None,
) -> tuple[Any, Any]:
    launch_options: dict[str, Any] = {
        "headless": headless,
        "slow_mo": 120,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    }
    if proxy_port is not None:
        launch_options["proxy"] = {"server": f"http://127.0.0.1:{proxy_port}"}

    browser = await playwright.chromium.launch(
        **launch_options,
    )
    context = await browser.new_context(
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
        user_agent=user_agent,
    )
    return browser, context


async def run_search_query(
    playwright: Any,
    query: str,
    headless: bool,
    proxy_port: int | None,
) -> SearchSessionResult:
    user_agent = choose_user_agent()
    browser = None
    context = None
    try:
        browser, context = await create_context(playwright, headless, user_agent, proxy_port)
        page = await context.new_page()
        page_text, results, final_url = await search_google(page, query)
        return SearchSessionResult(
            page_text=page_text,
            results=results,
            final_url=final_url,
            user_agent=user_agent,
            proxy_port=proxy_port,
        )
    except SearchRequestError:
        raise
    except Exception as exc:
        message = str(exc) or repr(exc)
        raise SearchRequestError(message, retryable=_is_retryable_error_message(message)) from exc
    finally:
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()


async def search_google(page: Any, query: str) -> tuple[str, list[dict[str, str]], str]:
    timeout_error = _get_playwright_timeout_error()
    search_url = "https://www.google.com/search?q=" + quote_plus(query)
    try:
        response = await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    except timeout_error as exc:
        raise SearchRequestError(f"request timeout for query: {query}", retryable=True) from exc
    except Exception as exc:
        message = str(exc) or repr(exc)
        raise SearchRequestError(message, retryable=_is_retryable_error_message(message)) from exc

    status_code = response.status if response is not None else None
    if status_code == 429 or (status_code is not None and status_code >= 500):
        raise SearchRequestError(
            f"temporary HTTP {status_code} for query: {query}",
            retryable=True,
            status_code=status_code,
        )

    await page.wait_for_timeout(4000)

    try:
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(1500)
    except Exception:
        pass

    try:
        page_text = await page.locator("body").inner_text(timeout=20000)
    except timeout_error as exc:
        raise SearchRequestError(f"page text timeout for query: {query}", retryable=True) from exc
    except Exception as exc:
        message = str(exc) or repr(exc)
        raise SearchRequestError(message, retryable=_is_retryable_error_message(message)) from exc

    results = await extract_search_results(page)
    return page_text, results, page.url


async def extract_search_results(page: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    headings = page.locator("a:has(h3)")
    count = min(await headings.count(), 5)

    for index in range(count):
        item = headings.nth(index)
        try:
            title = (await item.locator("h3").inner_text(timeout=3000)).strip()
            href = (await item.get_attribute("href")) or ""
        except Exception:
            continue
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        results.append({"title": title, "url": href})

    return results
