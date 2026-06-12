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
    proxy_ports: list[int]
    retry_attempts: int
    retry_delay_min: float
    retry_delay_max: float
    max_rows: int | None
    prepare_only: bool
    llm_api_base: str
    llm_api_key: str
    llm_model: str
    user_data_dir: str
    resolve_captcha: bool
    # DeepSeek AI Overview parser options (mutually exclusive with browser mode)
    ds_parse: bool = False
    ds_input: str = ""
    ds_output: str = ""
    ds_api_key: str = ""
    ds_api_base: str = ""
    ds_model: str = ""


DEFAULT_PROXY_PORTS = [7892]


def parse_proxy_ports(raw_value: str) -> list[int]:
    if not raw_value.strip():
        return []

    ports: list[int] = []
    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        ports.append(int(token))
    return ports


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
    parser.add_argument(
        "--proxy-ports",
        default=os.getenv("LOCAL_PROXY_PORTS", ",".join(str(port) for port in DEFAULT_PROXY_PORTS)),
        help="Comma-separated local proxy ports, e.g. 10001,10002,10003. Leave empty to disable port rotation.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=2,
        help="Maximum number of retries for retryable network failures.",
    )
    parser.add_argument(
        "--retry-delay-min",
        type=float,
        default=5.0,
        help="Minimum delay in seconds before retrying a failed request.",
    )
    parser.add_argument(
        "--retry-delay-max",
        type=float,
        default=15.0,
        help="Maximum delay in seconds before retrying a failed request.",
    )
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
        "--user-data-dir",
        default=str(base_dir / "browser_profile"),
        help=(
            "Path to the browser user data directory for persistent sessions. "
            "Saves cookies and login state so you only need to solve "
            "Google CAPTCHA once. Default: ./browser_profile"
        ),
    )
    parser.add_argument(
        "--resolve-captcha",
        action="store_true",
        help=(
            "Open Google in visible mode so you can manually solve the CAPTCHA once. "
            "The session cookie will be saved to --user-data-dir for reuse. "
            "After solving, close the browser window and re-run with --headless."
        ),
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("LLM_MODEL", "").strip(),
        help="Model name for the LLM classification step.",
    )

    # ---- DeepSeek AI Overview parser ----
    parser.add_argument(
        "--ds-parse",
        action="store_true",
        help="Run DeepSeek AI Overview parser instead of browser evidence collection.",
    )
    parser.add_argument(
        "--ds-input",
        default="",
        help="Input CSV path for DeepSeek parser (default: ./ai_overview_input.csv).",
    )
    parser.add_argument(
        "--ds-output",
        default="",
        help="Output CSV path for DeepSeek parser (default: ./ai_overview_parsed.csv).",
    )
    parser.add_argument(
        "--ds-api-key",
        default=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        help="API key for DeepSeek (or set DEEPSEEK_API_KEY env var).",
    )
    parser.add_argument(
        "--ds-api-base",
        default=os.getenv("DS_API_BASE", "https://api.deepseek.com").strip(),
        help="API base URL for DeepSeek parser (default: https://api.deepseek.com).",
    )
    parser.add_argument(
        "--ds-model",
        default=os.getenv("DS_MODEL", "deepseek-v4-flash").strip(),
        help="Model name for DeepSeek parser (default: deepseek-v4-flash).",
    )

    args = parser.parse_args()
    retry_delay_min = max(0.0, args.retry_delay_min)
    retry_delay_max = max(retry_delay_min, args.retry_delay_max)
    return AppConfig(
        input_path=Path(args.input).resolve(),
        output_path=Path(args.output).resolve(),
        headless=args.headless,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        proxy_ports=parse_proxy_ports(args.proxy_ports),
        retry_attempts=max(0, args.retry_attempts),
        retry_delay_min=retry_delay_min,
        retry_delay_max=retry_delay_max,
        max_rows=args.max_rows,
        prepare_only=args.prepare_only,
        llm_api_base=args.llm_api_base.rstrip("/"),
        llm_api_key=args.llm_api_key,
        llm_model=args.llm_model,
        user_data_dir=args.user_data_dir,
        resolve_captcha=args.resolve_captcha,
        ds_parse=args.ds_parse,
        ds_input=args.ds_input,
        ds_output=args.ds_output,
        ds_api_key=args.ds_api_key,
        ds_api_base=args.ds_api_base.rstrip("/"),
        ds_model=args.ds_model,
    )
