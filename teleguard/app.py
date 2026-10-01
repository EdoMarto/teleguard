"""Entry point: start the bot (long polling)."""

from __future__ import annotations

import logging

from telegram import Update

from .bot import build_application
from .config import Config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = build_application(Config.from_env())
    # chat_member updates must be requested explicitly.
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
