import json
from urllib import error, request

import pandas as pd

from .config import AppConfig
from .constants import COUNTY_COL, VALUE_COL, YEAR_COL
from .evidence import extract_evidence_excerpt


def llm_enabled(config: AppConfig) -> bool:
    return bool(config.llm_api_base and config.llm_api_key and config.llm_model)


def build_llm_prompt(row: pd.Series, page_text: str, source_title: str, source_url: str) -> str:
    year = str(row.get(YEAR_COL, "")).strip()
    county = str(row.get(COUNTY_COL, "")).strip()
    evidence_excerpt = extract_evidence_excerpt(page_text)
    return (
        "You are classifying crawled evidence for statistical yearbook missing-value review.\n"
        "Return JSON only. No markdown.\n"
        "Required keys: source_type, evidence_level, value_candidates, suggested_fill_value, "
        "unit, unit_flag, metric_conflict_flag, confidence, need_manual_check, review_notes.\n"
        "Constraints:\n"
        '- source_type must be one of: official_stats_bureau, government, yearbook_or_bulletin, search_summary, other_web_source\n'
        '- evidence_level must be one of: A, B, C\n'
        '- unit_flag must be one of: ok, conflict, missing\n'
        '- metric_conflict_flag must be "yes" or "no"\n'
        '- confidence must be one of: high, medium, low\n'
        '- need_manual_check must be "yes" or "no"\n'
        '- value_candidates must be an array of strings\n\n'
        f"Year: {year}\n"
        f"County: {county}\n"
        f"Target metric: {VALUE_COL}\n"
        f"Source title: {source_title}\n"
        f"Source url: {source_url}\n"
        "Evidence text:\n"
        f"{evidence_excerpt}"
    )


def call_openai_compatible_api(config: AppConfig, prompt: str) -> dict:
    payload = {
        "model": config.llm_model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify evidence for empirical research data review. "
                    "Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        url=f"{config.llm_api_base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.llm_api_key}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def merge_llm_classification(
    base_update: dict,
    llm_result: dict,
    config: AppConfig,
) -> dict:
    value_candidates = llm_result.get("value_candidates", [])
    if isinstance(value_candidates, list):
        value_candidates_text = "; ".join(str(item) for item in value_candidates if str(item).strip())
    else:
        value_candidates_text = str(value_candidates).strip()

    merged = dict(base_update)
    merged.update(
        {
            "source_type": llm_result.get("source_type", base_update["source_type"]),
            "evidence_level": llm_result.get("evidence_level", base_update["evidence_level"]),
            "value_candidates": value_candidates_text or base_update["value_candidates"],
            "suggested_fill_value": str(
                llm_result.get("suggested_fill_value", base_update["suggested_fill_value"])
            ).strip(),
            "unit": str(llm_result.get("unit", base_update["unit"])).strip(),
            "unit_flag": str(llm_result.get("unit_flag", base_update["unit_flag"])).strip(),
            "metric_conflict_flag": str(
                llm_result.get("metric_conflict_flag", base_update["metric_conflict_flag"])
            ).strip(),
            "confidence": str(llm_result.get("confidence", base_update["confidence"])).strip(),
            "need_manual_check": str(
                llm_result.get("need_manual_check", base_update["need_manual_check"])
            ).strip(),
            "review_notes": str(llm_result.get("review_notes", "")).strip(),
            "llm_provider": config.llm_api_base,
            "llm_model": config.llm_model,
            "llm_status": "success",
            "llm_structured_output": json.dumps(llm_result, ensure_ascii=False),
        }
    )
    return merged


def classify_with_optional_llm(
    row: pd.Series,
    page_text: str,
    source_title: str,
    source_url: str,
    base_update: dict,
    config: AppConfig,
) -> dict:
    if not llm_enabled(config):
        base_update["llm_status"] = "disabled"
        return base_update

    prompt = build_llm_prompt(row, page_text, source_title, source_url)
    try:
        llm_result = call_openai_compatible_api(config, prompt)
        return merge_llm_classification(base_update, llm_result, config)
    except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
        fallback = dict(base_update)
        fallback["llm_provider"] = config.llm_api_base
        fallback["llm_model"] = config.llm_model
        fallback["llm_status"] = f"failed: {repr(exc)}"
        return fallback
