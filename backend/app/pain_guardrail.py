"""
Pain guardrail: keyword listener for safety.
When transcript contains pain keywords, the agent must clear speech buffer
and deliver a safety warning. No PHI/PII in logs.
"""

from __future__ import annotations

PAIN_KEYWORDS = frozenset({"ouch", "hurts", "pain", "stop"})

SAFETY_WARNING = (
    "Stop the exercise immediately. I'm not a doctor. "
    "If you're in pain, please consult a healthcare provider before continuing."
)


def check_pain_keywords(transcript: str) -> bool:
    """
    Returns True if the transcript contains any pain keyword (case-insensitive).
    """
    if not transcript or not transcript.strip():
        return False
    lower = transcript.strip().lower()
    words = set(lower.split())
    return bool(words & PAIN_KEYWORDS) or any(
        kw in lower for kw in PAIN_KEYWORDS
    )
