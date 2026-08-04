"""
Pain guardrail: keyword listener for safety.
When transcript contains pain keywords, the agent must clear speech buffer
and deliver a safety warning. No PHI/PII in logs.
"""

from __future__ import annotations

import re

PAIN_KEYWORDS = frozenset({"ouch", "hurt", "hurts", "pain", "stop"})
_PAIN_PATTERN = re.compile(r"\b(?:ouch|hurt|hurts|pain|stop)\b", re.IGNORECASE)
_IMMEDIATE_PATTERN = re.compile(r"\b(?:ouch|stop)\b", re.IGNORECASE)

SAFETY_WARNING = (
    "Stop the exercise immediately. I'm not a doctor. "
    "If you're in pain, please consult a healthcare provider before continuing."
)


def normalize_transcript(transcript: str) -> str:
    """Stable key for transcript dedupe; punctuation and case do not matter."""
    return " ".join(re.findall(r"[a-z0-9]+", transcript.lower()))


def check_pain_keywords(transcript: str) -> bool:
    """Match standalone pain/safety words, never substrings such as ``stopping``."""
    return bool(transcript and _PAIN_PATTERN.search(transcript))


def claim_pain_event(transcript: str, handled: set[str]) -> bool:
    """Atomically claim a new pain transcript for one session's safety latch."""
    key = normalize_transcript(transcript)
    if not key or key in handled or not check_pain_keywords(transcript):
        return False
    handled.add(key)
    return True


def should_handle_pain_transcript(transcript: str, *, is_final: bool) -> bool:
    """Handle stop/ouch on interim input; wait for final text for other symptoms."""
    return bool(transcript and (is_final or _IMMEDIATE_PATTERN.search(transcript)) and check_pain_keywords(transcript))
