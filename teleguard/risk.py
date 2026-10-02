"""Score a new member's profile for spam/bot risk. Pure logic, easy to test."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Links, invite links and @handles hidden in a display name are a strong signal.
_LINK_RE = re.compile(r"(https?://|t\.me/|telegram\.me/|@\w{4,})", re.IGNORECASE)

_SPAM_WORDS = {
    "crypto", "bitcoin", "forex", "investment", "earn", "profit", "casino", "betting",
    "porn", "onlyfans", "sexy", "nude", "dating", "free money", "giveaway", "promo",
    "binary", "trading signals", "pump", "airdrop", "nft",
}


@dataclass
class Profile:
    user_id: int
    first_name: str
    last_name: str = ""
    username: str | None = None
    has_photo: bool = False
    datacenter: int | None = None  # from fileid.datacenter_from_file_id
    is_premium: bool = False


@dataclass
class RiskConfig:
    # Datacenters the admin considers suspicious (empty by default: DC is informational).
    suspicious_datacenters: set[int] = field(default_factory=set)
    # Score at or above which a member is treated as suspicious.
    threshold: int = 4


def _has_mixed_scripts(text: str) -> bool:
    """True if the name mixes e.g. Latin and Cyrillic, a common spoofing trick."""
    scripts = set()
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            if "CYRILLIC" in name:
                scripts.add("cyrillic")
            elif "LATIN" in name:
                scripts.add("latin")
    return len(scripts) > 1


def score(profile: Profile, config: RiskConfig | None = None) -> tuple[int, list[str]]:
    """Return (risk_score, reasons). Higher means more likely spam/bot."""
    config = config or RiskConfig()
    name = f"{profile.first_name} {profile.last_name}".strip()
    lower = name.lower()
    points = 0
    reasons: list[str] = []

    def add(n: int, why: str) -> None:
        nonlocal points
        points += n
        reasons.append(why)

    if not profile.username:
        add(1, "no username")
    if not profile.has_photo:
        add(2, "no profile photo")
    if _LINK_RE.search(name):
        add(3, "link or @handle in name")
    if any(word in lower for word in _SPAM_WORDS):
        add(3, "spam keyword in name")
    if len(name) > 40:
        add(1, "unusually long name")
    if _has_mixed_scripts(name):
        add(2, "mixed scripts in name")
    if profile.is_premium:
        add(-1, "Telegram Premium")  # bots rarely pay for Premium
    if profile.datacenter in config.suspicious_datacenters:
        add(1, f"registered in DC{profile.datacenter}")

    return max(points, 0), reasons


def is_suspicious(profile: Profile, config: RiskConfig | None = None) -> bool:
    config = config or RiskConfig()
    return score(profile, config)[0] >= config.threshold
