# -*- coding: utf-8 -*-
"""
DeepSeek AI Overview Parser
============================

Parses CSV files containing AI overview text and links (e.g. from Google AI
Overviews) using DeepSeek (or any OpenAI-compatible API) to extract structured
rural income data.

This serves as a **post-processing step** for already-collected AI Overview
data, complementing the browser-based evidence collection pipeline.

Usage::

    sydf --ds-parse --ds-input input.csv --ds-output output.csv
    sydf --ds-parse --ds-input input.csv --ds-api-key sk-xxx

Environment variables::

    DEEPSEEK_API_KEY      API key (can also be passed via --ds-api-key)
    DS_MODEL              Model name (default: deepseek-v4-flash)

Output schema
-------------
- city, ent_code, ent_county, year  — row identifiers
- rural_income                       — extracted income value (float or null)
- type                               — DeepSeek-classified evidence level (A/B/C)
- type_keyword                       — keyword-based validation of evidence level
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class DsParserConfig:
    """Configuration for the DeepSeek AI Overview parser.

    Parameters
    ----------
    input_path : Path
        Path to the input CSV containing AI overview text and links.
    output_path : Path
        Path where the parsed results CSV will be written.
    text_col : str
        Name of the column containing AI overview text (default: ``ai_overview_text``).
    link_col : str
        Name of the column containing AI overview source links (default: ``ai_overview_links``).
    keep_cols : tuple of str
        Row-identifier columns preserved in the output.
    api_key : str
        DeepSeek (or OpenAI-compatible) API key.
    api_base : str
        API base URL (default: ``https://api.deepseek.com``).
    model : str
        Model name (default: ``deepseek-v4-flash``).
    temperature : float
        LLM sampling temperature (default: 0.0).
    max_tokens : int
        Maximum tokens per LLM response (default: 400).
    max_retries : int
        Number of retries on API failure (default: 3).
    delay : float
        Seconds to wait between API calls (default: 0.6).
    """

    input_path: Path = Path("ai_overview_input.csv")
    output_path: Path = Path("ai_overview_parsed.csv")
    text_col: str = "ai_overview_text"
    link_col: str = "ai_overview_links"
    keep_cols: tuple[str, ...] = ("city", "ent_code", "ent_county", "year")
    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.0
    max_tokens: int = 400
    max_retries: int = 3
    delay: float = 0.6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def safe_json_loads(s: str) -> dict[str, Any]:
    """Safely parse JSON from an LLM response, stripping markdown fences.

    Tries :func:`json.loads` directly first.  On failure, falls back to
    extracting the first ``{...}`` block via regex.
    """
    if not s:
        return {}
    s = s.strip()
    s = re.sub(r"^```json\s*", "", s)
    s = re.sub(r"^```\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}


def classify_source_keyword(links: str, text: str, is_prediction: bool) -> str:
    """Keyword-based source classification used as a side-by-side validation column.

    Returns
    -------
    str
        ``"C"`` if *is_prediction* is true, ``"A"`` if government/statistical
        keywords are found, ``"B"`` otherwise.
    """
    if is_prediction:
        return "C"

    links_lower = str(links or "").lower()
    text_lower = str(text or "").lower()

    a_keywords = [
        "统计局",
        "人民政府",
        "政府网",
        "gov.cn",
        ".gov.",
        "统计公报",
        "国民经济和社会发展统计公报",
        "政府工作报告",
        "统计年鉴",
        "地方志",
        "年鉴",
    ]
    b_keywords = [
        "ceic",
        "wind",
        "eps",
        "cnki",
        "百度百科",
        "搜狐",
        "网易",
        "腾讯",
        "新浪",
        "知乎",
        "豆丁",
        "道客",
        "中经数据",
        "权威数据库",
        "数据库",
    ]

    if any(k.lower() in links_lower or k.lower() in text_lower for k in a_keywords):
        return "A"
    if any(k.lower() in links_lower or k.lower() in text_lower for k in b_keywords):
        return "B"
    return "B"


def _build_ds_prompt(text: str, links: str, city: str, county: str, year) -> str:
    return f"""
你是严谨的数据抽取助手。请从下面文本中提取：
1. {year} 年 {county} / {city} 的农村居民人均可支配收入或人均纯收入（单位元）。
2. 如果是区间，如 "15000-17000元"，返回中位数 16000。
3. 如果是预测/估算/预计/推算，标记 is_prediction=true。
4. 同时根据来源和正文判断 type：
    A级：地方统计局 / 政府官网 / 官方统计公报 / 政府报告 / 统计年鉴
    B级：权威数据库 / 二手网页
    C级：预测数据
5. 如果无法获取收入，rural_income=null

文本：
{text}

来源链接：
{links}

返回严格 JSON，格式：
{{
  "rural_income": 12345.0 或 null,
  "is_prediction": true 或 false,
  "type": "A" / "B" / "C",
  "evidence": "最相关短句"
}}
"""


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def call_deepseek_extract(
    client: OpenAI,
    model: str,
    text: str,
    links: str,
    city: str,
    county: str,
    year,
    max_retries: int = 3,
    temperature: float = 0.0,
    max_tokens: int = 400,
) -> dict[str, Any]:
    """Call the DeepSeek API once, extracting structured income data.

    Retries up to *max_retries* times on transient API errors with
    exponential back-off (3 s, 6 s, 9 s …).

    Returns
    -------
    dict
        Keys: ``rural_income``, ``is_prediction``, ``type``, ``evidence``.
        On total failure after all retries, returns a safe fallback dict.
    """
    prompt = _build_ds_prompt(text, links, city, county, year)

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你只输出严格 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            return safe_json_loads(content)
        except Exception as e:
            print(f"  API failure, retry {attempt + 1}/{max_retries}: {e}")
            time.sleep(3 + attempt * 3)

    return {"rural_income": None, "is_prediction": False, "type": "B", "evidence": ""}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_ds_parser(config: DsParserConfig) -> None:
    """Run the DeepSeek AI Overview parsing pipeline.

    The pipeline:

    1. Reads the input CSV, validates required columns.
    2. Checks for an existing output CSV to **resume** from (rows already
       present are skipped, identified by the ``(city, ent_code, ent_county,
       year)`` composite key).
    3. For each new row, calls the DeepSeek API to extract income and evidence
       level, then writes the result incrementally (one row at a time) to the
       output file — safe to Ctrl+C and re-run.
    """
    if not config.api_key:
        raise ValueError(
            "DeepSeek API key is required. "
            "Set the DEEPSEEK_API_KEY environment variable or pass --ds-api-key."
        )

    df = pd.read_csv(config.input_path, encoding="utf-8-sig")
    for col in list(config.keep_cols) + [config.text_col, config.link_col]:
        if col not in df.columns:
            raise ValueError(f"Input CSV is missing required column: {col}")

    client = OpenAI(api_key=config.api_key, base_url=config.api_base)

    # ---- checkpoint / resume ----
    if config.output_path.exists():
        out_df = pd.read_csv(config.output_path, encoding="utf-8-sig")
        done_keys: set[tuple[str, ...]] = set(
            zip(
                out_df["city"].astype(str),
                out_df["ent_code"].astype(str),
                out_df["ent_county"].astype(str),
                out_df["year"].astype(str),
            )
        )
        results = out_df.to_dict("records")
        print(f"Found existing results ({len(results)} rows). Resuming.")
    else:
        done_keys = set()
        results = []

    total = len(df)
    pending = total - len(done_keys)
    print(f"Total: {total} rows, pending: {pending}.")

    # ---- main loop ----
    for idx, row in df.iterrows():
        key = (
            str(row["city"]),
            str(row["ent_code"]),
            str(row["ent_county"]),
            str(row["year"]),
        )
        if key in done_keys:
            continue

        text = str(row.get(config.text_col, "") or "")
        links = str(row.get(config.link_col, "") or "")

        print(f"[{idx + 1}/{total}] {row['year']} {row['city']} {row['ent_county']}")

        if not text.strip():
            # Empty AI Overview text — no point calling the API
            rural_income = None
            type_deepseek = "B"
            is_prediction = False
        else:
            extracted = call_deepseek_extract(
                client=client,
                model=config.model,
                text=text,
                links=links,
                city=row["city"],
                county=row["ent_county"],
                year=row["year"],
                max_retries=config.max_retries,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
            rural_income = extracted.get("rural_income")
            type_deepseek = extracted.get("type", "B")
            is_prediction = extracted.get("is_prediction", False)

        type_keyword = classify_source_keyword(links, text, is_prediction)

        result: dict[str, Any] = {
            "city": row["city"],
            "ent_code": row["ent_code"],
            "ent_county": row["ent_county"],
            "year": row["year"],
            "rural_income": rural_income,
            "type": type_deepseek,
            "type_keyword": type_keyword,
        }
        results.append(result)

        # Persist after every row — safe to interrupt and resume
        pd.DataFrame(results).to_csv(config.output_path, index=False, encoding="utf-8-sig")

        if pending > 1:
            time.sleep(config.delay)

    print(f"Done: {config.output_path}")
