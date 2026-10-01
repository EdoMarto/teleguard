"""Decide whether a message looks like spam. Pure logic, easy to test."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINK_RE = re.compile(r"(https?://|t\.me/|telegram\.me/|www\.)", re.IGNORECASE)
_HANDLE_RE = re.compile(r"@\w{4,}")
_SPAM_PHRASES = (
    "earn money", "work from home", "investment opportunity", "double your",
    "crypto signals", "join my channel", "click the link", "dm me", "100% profit",
    "limited offer", "make money", "free gift",
)


@dataclass
class SpamConfig:
    # Users with fewer than this many prior messages are "new" and watched harder.
    trust_after_messages: int = 3
    # New users may not post links or forwarded channel posts.
    block_links_from_new_users: bool = True
    max_mentions: int = 5


def is_spam(
    text: str,
    *,
    message_count: int,
    is_forwarded_from_channel: bool = False,
    config: SpamConfig | None = None,
) -> tuple[bool, str]:
    """Return (is_spam, reason). `message_count` is how many messages the user has sent before."""
    config = config or SpamConfig()
    lower = text.lower()
    is_new = message_count < config.trust_after_messages

    if any(phrase in lower for phrase in _SPAM_PHRASES):
        return True, "spam phrase"
    if len(_HANDLE_RE.findall(text)) > config.max_mentions:
        return True, "too many mentions"
    if is_new and config.block_links_from_new_users and _LINK_RE.search(text):
        return True, "link from a new user"
    if is_new and is_forwarded_from_channel:
        return True, "forwarded channel post from a new user"
    return False, ""
