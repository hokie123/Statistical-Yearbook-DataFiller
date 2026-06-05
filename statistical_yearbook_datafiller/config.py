import argparse
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    input_path: Path
    output_path: Path
    headless: bool
    sleep_min: float
    sleep_max: float
    max_rows: int | None
    prepare_only: bool
    llm_api_base: str
    llm_api_key: str
    llm_model: str


def parse_args(base_dir: Path) -> AppConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Collect traceable evidence for missing statistical yearbook values "
            "and write a manual-review-friendly output table."
        )
    )
    parser.add_argument("--input", default=str(base_dir / "data.csv"), help="Path to the input CSV file.")
    parser.add_argument(
        "--output",
        default=str(base_dir / "evidence_review_output.csv"),
        help="Path to the output CSV file.",
    )
    parser.add_argument("--headless", action="store_true", help="Run the browser in headless mode.")
    parser.add_argument("--sleep-min", type=float, default=3.0, help="Minimum delay between queries.")
    parser.add_argument("--sleep-max", type=float, default=6.0, help="Maximum delay between queries.")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit the number of rows to process.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only generate search queries and review columns without opening the browser.",
    )
    parser.add_argument(
        "--llm-api-base",
        default=os.getenv("LLM_API_BASE", "").strip(),
        help="OpenAI-compatible API base URL, e.g. https://api.openai.com/v1.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=os.getenv("LLM_API_KEY", "").strip(),
        help="API key for the LLM classification step.",
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("LLM_MODEL", "").strip(),
        help="Model name for the LLM classification step.",
    )
    args = parser.parse_args()
    return AppConfig(
        input_path=Path(args.input).resolve(),
        output_path=Path(args.output).resolve(),
        headless=args.headless,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        max_rows=args.max_rows,
        prepare_only=args.prepare_only,
        llm_api_base=args.llm_api_base.rstrip("/"),
        llm_api_key=args.llm_api_key,
        llm_model=args.llm_model,
    )
