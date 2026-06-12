import asyncio
from pathlib import Path

from .config import parse_args
from .ds_parser import DsParserConfig, run_ds_parser
from .pipeline import run_collection


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    config = parse_args(base_dir)

    # ---- DeepSeek AI Overview parser mode ----
    if config.ds_parse:
        import os

        ds_cfg = DsParserConfig(
            input_path=Path(config.ds_input).resolve()
            if config.ds_input
            else Path.cwd() / "ai_overview_input.csv",
            output_path=Path(config.ds_output).resolve()
            if config.ds_output
            else Path.cwd() / "ai_overview_parsed.csv",
            api_key=config.ds_api_key,
            api_base=config.ds_api_base,
            model=config.ds_model,
        )
        run_ds_parser(ds_cfg)
        return

    # ---- Normal browser-based evidence collection ----
    asyncio.run(run_collection(config))
