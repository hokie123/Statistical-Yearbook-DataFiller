import re

YEAR_COL = "year"
COUNTY_COL = "ent_county"
CODE_COL = "ent_code"
VALUE_COL = "rural_income"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

EVIDENCE_COLUMNS = [
    "search_query",
    "search_url",
    "fetch_status",
    "page_text_excerpt",
    "evidence_text",
    "source_title",
    "source_url",
    "source_domain",
    "source_type",
    "evidence_level",
    "evidence_year",
    "value_candidates",
    "suggested_fill_value",
    "unit",
    "confidence",
    "unit_flag",
    "metric_conflict_flag",
    "llm_provider",
    "llm_model",
    "llm_status",
    "llm_structured_output",
    "need_manual_check",
    "manual_review_status",
    "review_notes",
]

METRIC_KEYWORDS = {
    VALUE_COL: [
        "农村居民人均可支配收入",
        "农村居民人均收入",
        "农村居民可支配收入",
        "农村人均可支配收入",
    ]
}

UNIT_KEYWORDS = {
    "元": ["元"],
    "万元": ["万元", "万 元"],
    "亿元": ["亿元", "亿 元"],
    "人": ["人"],
    "万人": ["万人", "万 人"],
}

SOURCE_PATTERNS = {
    "yearbook_or_bulletin": ["年鉴", "统计公报", "国民经济和社会发展"],
}

NUMERIC_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)")
