"""Entry point: python -m bot"""
import asyncio
import sys

from bot.app import run
from bot.config import Config, ConfigError, load_dotenv
from bot.logging_setup import setup_logging


def main() -> None:
    load_dotenv()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(2)
    setup_logging(config.log_level, config.log_format)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
