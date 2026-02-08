"""
Exercise database service for FlexFlow.
Loads the free-exercise-db (873 exercises, all with images) from GitHub
into memory on first use, then searches locally.
No API key required. Images hosted on GitHub raw CDN.

Search uses:
  1. Synonym expansion (trapezius → traps, etc.)
  2. Name matching (exact → substring → word overlap)
  3. Muscle-group matching (primary > secondary)
  4. Category boosting (prefer "stretching" when query mentions stretch)
  5. Penalty for generic-only matches ("stretch", "upper", "side")
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("flexflow.exercise_db")

_EXERCISES_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db"
    "/main/dist/exercises.json"
)
_IMAGE_BASE = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db"
    "/main/exercises"
)

_cache: list[dict[str, Any]] | None = None
_name_index: dict[str, dict[str, Any]] | None = None

# ── Synonym map ──────────────────────────────────────────────────────
# Maps common PT terms to the muscle names used in the database.
_SYNONYMS: dict[str, list[str]] = {
    "trapezius": ["traps"],
    "trap": ["traps"],
    "traps": ["traps"],
    "upper trap": ["traps", "neck"],
    "upper trapezius": ["traps", "neck"],
    "lat": ["lats"],
    "latissimus": ["lats"],
    "pec": ["chest"],
    "pecs": ["chest"],
    "pectoral": ["chest"],
    "quad": ["quadriceps"],
    "quads": ["quadriceps"],
    "hammy": ["hamstrings"],
    "hammies": ["hamstrings"],
    "ham": ["hamstrings"],
    "glute": ["glutes"],
    "gluteal": ["glutes"],
    "ab": ["abdominals"],
    "abs": ["abdominals"],
    "core": ["abdominals", "lower back"],
    "calf": ["calves"],
    "forearm": ["forearms"],
    "bicep": ["biceps"],
    "tricep": ["triceps"],
    "delt": ["shoulders"],
    "delts": ["shoulders"],
    "deltoid": ["shoulders"],
    "rotator cuff": ["shoulders"],
    "rhomboid": ["middle back"],
    "mid back": ["middle back"],
    "upper back": ["middle back", "traps"],
    "lower back": ["lower back"],
    "lumbar": ["lower back"],
    "cervical": ["neck"],
    "hip flexor": ["quadriceps"],
    "groin": ["adductors"],
    "inner thigh": ["adductors"],
    "outer thigh": ["abductors"],
    "it band": ["abductors"],
    "wrist": ["forearms"],
}

# Words that are too generic to drive a match on their own.
_GENERIC_WORDS = {"stretch", "stretching", "exercise", "upper", "lower",
                  "side", "front", "back", "the", "a", "and", "on", "to",
                  "with", "for", "of", "left", "right", "seated", "standing"}


async def _load_exercises() -> list[dict[str, Any]]:
    """Download and cache the exercise database on first call."""
    global _cache, _name_index
    if _cache is not None:
        return _cache
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(_EXERCISES_URL)
            r.raise_for_status()
            _cache = r.json()
            _name_index = {
                str(ex.get("name", "")).lower(): ex for ex in _cache if ex.get("name")
            }
            logger.info("Loaded %d exercises from free-exercise-db", len(_cache))
            return _cache
    except Exception:
        logger.exception("Failed to load exercise database")
        return []


def _tokenize(text: str) -> list[str]:
    """Split into lowercase alpha tokens."""
    return re.findall(r"[a-z]+", text.lower())


def _expand_synonyms(query: str) -> set[str]:
    """Return muscle names that the query might be referring to."""
    muscles: set[str] = set()
    q = query.lower()
    for phrase, targets in _SYNONYMS.items():
        if phrase in q:
            muscles.update(targets)
    return muscles


_QUERY_OVERRIDES: dict[str, str] = {
    "upper trapezius stretch": "Side Neck Stretch",
    "upper trap stretch": "Side Neck Stretch",
    "trap stretch": "Side Neck Stretch",
    "trapezius stretch": "Side Neck Stretch",
    "neck lateral flexion": "Side Neck Stretch",
    "neck rotation stretch": "Neck-SMR",
    "upper back stretch": "Upper Back Stretch",
    "lower back stretch": "Chair Lower Back Stretch",
    "shoulder cross body stretch": "Shoulder Stretch",
    "chest opener stretch": "Behind Head Chest Stretch",
    "cat cow": "Cat Stretch",
}


def _override_match(query: str) -> dict[str, Any] | None:
    if _name_index is None:
        return None
    q = query.lower().strip()
    for key, name in _QUERY_OVERRIDES.items():
        if key in q:
            return _name_index.get(name.lower())
    return None


def _score(query: str, exercise: dict[str, Any]) -> float:
    """
    Score an exercise against a query.  Higher = better match.
    Returns 0 for no match.
    """
    q_lower = query.lower().strip()
    name_lower = exercise.get("name", "").lower()
    q_tokens = _tokenize(q_lower)
    name_tokens = set(_tokenize(name_lower))
    primary = [m.lower() for m in exercise.get("primaryMuscles", [])]
    secondary = [m.lower() for m in exercise.get("secondaryMuscles", [])]
    all_muscles = set(primary + secondary)
    category = exercise.get("category", "").lower()

    score = 0.0

    # ── 1. Name matching ────────────────────────────────────────────
    if q_lower == name_lower:
        score += 100
    elif q_lower in name_lower:
        score += 80
    else:
        meaningful = [t for t in q_tokens if t not in _GENERIC_WORDS]
        generic = [t for t in q_tokens if t in _GENERIC_WORDS]
        meaningful_hits = sum(1 for t in meaningful if t in name_tokens)
        generic_hits = sum(1 for t in generic if t in name_tokens)

        if meaningful and meaningful_hits > 0:
            score += (meaningful_hits / len(meaningful)) * 60
            score += generic_hits * 2
        elif generic_hits > 0:
            score += generic_hits * 3
        else:
            pass

    # ── 2. Muscle matching ──────────────────────────────────────────
    target_muscles = _expand_synonyms(q_lower)
    if target_muscles:
        primary_hits = len(target_muscles & set(primary))
        secondary_hits = len(target_muscles & set(secondary))
        if primary_hits > 0:
            score += 40 * primary_hits
        if secondary_hits > 0:
            score += 15 * secondary_hits

    # ── 3. Category boosting ────────────────────────────────────────
    wants_stretch = any(w in q_lower for w in ["stretch", "stretching", "flexibility"])
    if wants_stretch and category == "stretching":
        score += 25
    elif wants_stretch and category != "stretching":
        score -= 10

    # ── 4. Penalty for generic-only matches ─────────────────────────
    if score > 0:
        meaningful = [t for t in q_tokens if t not in _GENERIC_WORDS]
        if meaningful:
            meaningful_in_name = sum(1 for t in meaningful if t in name_tokens)
            meaningful_in_muscles = len(target_muscles & all_muscles)
            if meaningful_in_name == 0 and meaningful_in_muscles == 0:
                score *= 0.1

    # ── 5. Cross-validation: query implies muscles but exercise misses them
    if target_muscles and score > 0:
        if not (target_muscles & all_muscles):
            score *= 0.2

    return score


async def search_exercise(name: str) -> dict[str, Any] | None:
    """
    Search the exercise database by name. Returns the best match with
    image_url, name, instructions, category, and muscles.
    """
    exercises = await _load_exercises()
    if not exercises:
        return None

    override = _override_match(name)
    if override is not None:
        best = override
        best_score = 100.0
    else:
        best = None
        best_score = 0.0

    if best is None:
        for ex in exercises:
            s = _score(name, ex)
            if s > best_score:
                best_score = s
                best = ex

    if best is None or best_score < 15:
        return None

    images = best.get("images", [])
    image_url = f"{_IMAGE_BASE}/{images[0]}" if images else ""
    image_url_end = f"{_IMAGE_BASE}/{images[1]}" if len(images) > 1 else ""

    return {
        "name": best.get("name", ""),
        "image_url": image_url,
        "image_url_end": image_url_end,
        "instructions": best.get("instructions", []),
        "category": best.get("category", ""),
        "primary_muscles": best.get("primaryMuscles", []),
        "secondary_muscles": best.get("secondaryMuscles", []),
        "equipment": best.get("equipment", ""),
    }


async def search_exercises(name: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return up to `limit` matching exercises sorted by relevance."""
    exercises = await _load_exercises()
    if not exercises:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for ex in exercises:
        s = _score(name, ex)
        if s >= 5:
            scored.append((s, ex))

    scored.sort(key=lambda t: t[0], reverse=True)
    results: list[dict[str, Any]] = []

    for _s, ex in scored[:limit]:
        images = ex.get("images", [])
        results.append({
            "name": ex.get("name", ""),
            "image_url": f"{_IMAGE_BASE}/{images[0]}" if images else "",
            "category": ex.get("category", ""),
            "primary_muscles": ex.get("primaryMuscles", []),
        })

    return results
