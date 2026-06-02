import asyncio
import random
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright

# 自动获取当前脚本所在的文件夹
BASE_DIR = Path(__file__).parent

# 寻找当前文件夹下一个名叫 "data.csv" 的文件
input_path = BASE_DIR / "data.csv"
output_path = BASE_DIR / "experimental_group_google_evidence.csv"

YEAR_COL = "year"
COUNTY_COL = "ent_county"
CODE_COL = "ent_code"
VALUE_COL = "rural_income"

HEADLESS = False
SLEEP_MIN = 5
SLEEP_MAX = 10
MAX_ROWS = None  # 测试时可改成 20


def build_query(row):
    year = str(row[YEAR_COL]).strip()
    county = str(row[COUNTY_COL]).strip()
    return f"{year}年 {county} 农村居民人均可支配收入"


def extract_evidence(text):
    keywords = [
        "AI 概览",
        "AI Overview",
        "农村居民人均可支配收入",
        "农村居民人均收入",
        "人均可支配收入",
        "统计公报",
    ]

    hits = []
    text = text.replace("\r", "\n")

    for kw in keywords:
        pos = text.find(kw)
        if pos != -1:
            start = max(0, pos - 800)
            end = min(len(text), pos + 2000)
            hits.append(text[start:end])

    if hits:
        return "\n\n--- evidence split ---\n\n".join(hits)

    return text[:3000]


async def search_google(page, query):
    url = "https://www.google.com/search?q=" + query.replace(" ", "+")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    await page.wait_for_timeout(5000)

    try:
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(2000)
    except Exception:
        pass

    text = await page.locator("body").inner_text(timeout=20000)
    return text


async def main():
    df = pd.read_csv(input_path, dtype={CODE_COL: str})

    if "google_query" not in df.columns:
        df["google_query"] = ""
    if "google_page_text" not in df.columns:
        df["google_page_text"] = ""
    if "google_evidence_text" not in df.columns:
        df["google_evidence_text"] = ""
    if "google_fetch_status" not in df.columns:
        df["google_fetch_status"] = ""

    mask = df[VALUE_COL].isna() | (df[VALUE_COL].astype(str).str.strip() == "")

    target_indices = list(df[mask].index)
    if MAX_ROWS is not None:
        target_indices = target_indices[:MAX_ROWS]

    print(f"需要抓取证据的行数：{len(target_indices)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            slow_mo=200,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        context = await browser.new_context(
            locale="zh-CN",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        for n, idx in enumerate(target_indices, start=1):
            row = df.loc[idx]
            query = build_query(row)

            print(f"[{n}/{len(target_indices)}] {query}")

            try:
                text = await search_google(page, query)
                evidence = extract_evidence(text)

                df.at[idx, "google_query"] = query
                df.at[idx, "google_page_text"] = text[:15000]
                df.at[idx, "google_evidence_text"] = evidence[:5000]
                df.at[idx, "google_fetch_status"] = "success"

            except Exception as e:
                df.at[idx, "google_query"] = query
                df.at[idx, "google_fetch_status"] = f"failed: {repr(e)}"
                print(f"失败：{repr(e)}")

            df.to_csv(output_path, index=False, encoding="utf-8-sig")

            sleep_time = random.uniform(SLEEP_MIN, SLEEP_MAX)
            await page.wait_for_timeout(int(sleep_time * 1000))

        await browser.close()

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"完成，结果保存到：{output_path}")


if __name__ == "__main__":
    asyncio.run(main())
