"""Configuration, read from environment variables (and a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


def _int_set(value: str) -> set[int]:
    return {int(x) for x in value.replace(",", " ").split() if x.strip().isdigit()}


@dataclass
class Config:
    token: str | None
    captcha_timeout: int  # seconds to solve the join challenge
    flood_max: int  # messages ...
    flood_seconds: float  # ... within this window triggers a mute
    warn_limit: int  # warnings before an automatic ban
    risk_threshold: int  # risk score treated as suspicious
    suspicious_datacenters: set[int]
    welcome_text: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            captcha_timeout=int(os.environ.get("CAPTCHA_TIMEOUT", "60")),
            flood_max=int(os.environ.get("FLOOD_MAX", "5")),
            flood_seconds=float(os.environ.get("FLOOD_SECONDS", "5")),
            warn_limit=int(os.environ.get("WARN_LIMIT", "3")),
            risk_threshold=int(os.environ.get("RISK_THRESHOLD", "4")),
            suspicious_datacenters=_int_set(os.environ.get("SUSPICIOUS_DATACENTERS", "")),
            welcome_text=os.environ.get("WELCOME_TEXT", "Benvenuto/a nel gruppo! 👋"),
        )
