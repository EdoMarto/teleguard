"""Per-user flood detection: too many messages in a short window."""

from __future__ import annotations

from collections import defaultdict, deque


class FloodTracker:
    def __init__(self, max_messages: int = 5, per_seconds: float = 5.0) -> None:
        self.max_messages = max_messages
        self.per_seconds = per_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def is_flooding(self, user_id: int, now: float) -> bool:
        """Record a message at time `now` (seconds) and report if the user is flooding."""
        hits = self._hits[user_id]
        hits.append(now)
        while hits and now - hits[0] > self.per_seconds:
            hits.popleft()
        return len(hits) > self.max_messages

    def reset(self, user_id: int) -> None:
        self._hits.pop(user_id, None)
