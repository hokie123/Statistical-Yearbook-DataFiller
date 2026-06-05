from typing import Any
from urllib.parse import quote_plus

from .constants import DEFAULT_USER_AGENT


async def create_context(playwright: Any, headless: bool) -> Any:
    browser = await playwright.chromium.launch(
        headless=headless,
        slow_mo=120,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    context = await browser.new_context(
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
        user_agent=DEFAULT_USER_AGENT,
    )
    return context


async def search_google(page: Any, query: str) -> tuple[str, list[dict[str, str]]]:
    search_url = "https://www.google.com/search?q=" + quote_plus(query)
    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4000)

    try:
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(1500)
    except Exception:
        pass

    page_text = await page.locator("body").inner_text(timeout=20000)
    results = await extract_search_results(page)
    return page_text, results


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
