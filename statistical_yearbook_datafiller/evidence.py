import math
from typing import Any
from urllib.parse import quote_plus, urlparse

import pandas as pd

from .constants import (
    COUNTY_COL,
    EVIDENCE_COLUMNS,
    METRIC_KEYWORDS,
    NUMERIC_PATTERN,
    SOURCE_PATTERNS,
    UNIT_KEYWORDS,
    VALUE_COL,
    YEAR_COL,
)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in EVIDENCE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df


def build_queries(row: pd.Series) -> list[str]:
    year = str(row.get(YEAR_COL, "")).strip()
    county = str(row.get(COUNTY_COL, "")).strip()
    metric_aliases = METRIC_KEYWORDS.get(VALUE_COL, [VALUE_COL])
    queries = []

    for metric in metric_aliases:
        queries.append(f"{year}年 {county} {metric}")
        queries.append(f"{year}年 {county} {metric} 统计公报")
        queries.append(f"{year}年 {county} 国民经济和社会发展统计公报 {metric}")

    deduped = []
    seen = set()
    for query in queries:
        if query not in seen:
            deduped.append(query)
            seen.add(query)
    return deduped


def choose_primary_query(row: pd.Series) -> str:
    return build_queries(row)[0]


def extract_evidence_excerpt(text: str) -> str:
    keywords = [
        "AI 概览",
        "AI Overview",
        "统计公报",
        "农村居民人均可支配收入",
        "农村居民人均收入",
        "可支配收入",
    ]
    clean_text = text.replace("\r", "\n")
    snippets: list[str] = []
    for keyword in keywords:
        pos = clean_text.find(keyword)
        if pos == -1:
            continue
        start = max(0, pos - 600)
        end = min(len(clean_text), pos + 1800)
        snippet = clean_text[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    if snippets:
        return "\n\n--- evidence split ---\n\n".join(snippets)[:8000]
    return clean_text[:4000]


def extract_numeric_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in NUMERIC_PATTERN.finditer(text):
        token = match.group(1).replace(",", "")
        if len(token) >= 4 or "." in token:
            candidates.append(token)
    seen = set()
    ordered = []
    for item in candidates:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered[:8]


def detect_unit(text: str) -> tuple[str, str]:
    detected_units = []
    for unit, aliases in UNIT_KEYWORDS.items():
        if any(alias in text for alias in aliases):
            detected_units.append(unit)
    if not detected_units:
        return "", "missing"
    if len(set(detected_units)) > 1:
        return "/".join(detected_units), "conflict"
    return detected_units[0], "ok"


def detect_metric_conflict(text: str) -> bool:
    metric_terms = METRIC_KEYWORDS.get(VALUE_COL, [])
    broad_terms = ["居民人均可支配收入", "城镇居民人均可支配收入", "本外币贷款余额", "人民币贷款余额"]
    text_terms = [term for term in metric_terms + broad_terms if term in text]
    return "农村居民人均可支配收入" not in text_terms and len(text_terms) > 0


def classify_source(url: str, evidence_text: str) -> tuple[str, str]:
    url_lower = url.lower()
    if "stats.gov.cn" in url_lower or ".tjj." in url_lower:
        return "official_stats_bureau", "A"
    if ".gov." in url_lower or url_lower.endswith(".gov.cn"):
        return "government", "A"
    if "yearbook" in url_lower or any(token in evidence_text for token in SOURCE_PATTERNS["yearbook_or_bulletin"]):
        return "yearbook_or_bulletin", "B"
    if any(token.lower() in url_lower for token in ["google.com", "bing.com", "baidu.com"]):
        return "search_summary", "C"
    return "other_web_source", "C"


def infer_confidence(level: str, has_value: bool, unit_flag: str, metric_conflict: bool) -> str:
    if not has_value:
        return "low"
    if level == "A" and unit_flag == "ok" and not metric_conflict:
        return "high"
    if level in {"A", "B"} and unit_flag != "conflict":
        return "medium"
    return "low"


def build_record_update(
    row: pd.Series,
    query: str,
    page_text: str,
    source_title: str,
    source_url: str,
) -> dict[str, Any]:
    evidence_text = extract_evidence_excerpt(page_text)
    candidates = extract_numeric_candidates(evidence_text)
    source_type, evidence_level = classify_source(source_url, evidence_text)
    unit, unit_flag = detect_unit(evidence_text)
    metric_conflict = detect_metric_conflict(evidence_text)
    suggested_value = candidates[0] if candidates else ""
    confidence = infer_confidence(
        evidence_level,
        has_value=bool(suggested_value),
        unit_flag=unit_flag,
        metric_conflict=metric_conflict,
    )

    return {
        "search_query": query,
        "search_url": f"https://www.google.com/search?q={quote_plus(query)}",
        "fetch_status": "success",
        "page_text_excerpt": page_text[:12000],
        "evidence_text": evidence_text,
        "source_title": source_title,
        "source_url": source_url,
        "source_domain": urlparse(source_url).netloc if source_url else "",
        "source_type": source_type,
        "evidence_level": evidence_level,
        "evidence_year": str(row.get(YEAR_COL, "")).strip(),
        "value_candidates": "; ".join(candidates),
        "suggested_fill_value": suggested_value,
        "unit": unit,
        "confidence": confidence,
        "unit_flag": unit_flag,
        "metric_conflict_flag": "yes" if metric_conflict else "no",
        "llm_provider": "",
        "llm_model": "",
        "llm_status": "",
        "llm_structured_output": "",
        "need_manual_check": "yes" if confidence != "high" or len(candidates) != 1 else "no",
        "manual_review_status": "pending",
        "review_notes": "",
    }
