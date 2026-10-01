"""Build the join challenge: a simple question only a human bothers to answer."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Challenge:
    question: str
    answer: str
    options: list[str]  # shown as buttons; one of them equals `answer`


def make_challenge(harder: bool = False) -> Challenge:
    """A small arithmetic question. `harder` (for suspicious users) uses bigger numbers."""
    hi = 20 if harder else 9
    a, b = random.randint(2, hi), random.randint(2, hi)
    answer = str(a + b)

    options = {answer}
    while len(options) < 4:
        options.add(str(a + b + random.randint(-5, 5)))
    shuffled = list(options)
    random.shuffle(shuffled)

    return Challenge(question=f"Quanto fa {a} + {b}?", answer=answer, options=shuffled)
