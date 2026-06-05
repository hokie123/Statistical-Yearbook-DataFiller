import asyncio
from pathlib import Path

from .config import parse_args
from .pipeline import run_collection


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    config = parse_args(base_dir)
    asyncio.run(run_collection(config))
