"""
Static exercise resource map for FlexFlow.
Maps stretch IDs to YouTube embed URLs and thumbnail images
for common Neck, Shoulder, and Arm stretches.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


def _youtube_thumbnail(embed_url: str) -> str:
    """Extract video ID from a YouTube embed URL and return a thumbnail."""
    match = re.search(r"/embed/([A-Za-z0-9_-]+)", embed_url)
    if not match:
        return ""
    return f"https://img.youtube.com/vi/{match.group(1)}/hqdefault.jpg"


class ExerciseResource(BaseModel):
    id: str
    title: str
    youtube_embed_url: str
    thumbnail_url: str
    body_part: str
    description: str


def _res(
    id: str,
    title: str,
    youtube_embed_url: str,
    body_part: str,
    description: str,
) -> ExerciseResource:
    return ExerciseResource(
        id=id,
        title=title,
        youtube_embed_url=youtube_embed_url,
        thumbnail_url=_youtube_thumbnail(youtube_embed_url),
        body_part=body_part,
        description=description,
    )


EXERCISE_RESOURCES: dict[str, ExerciseResource] = {
    "neck_lateral_flexion": _res(
        id="neck_lateral_flexion",
        title="Neck Lateral Flexion Stretch",
        youtube_embed_url="https://www.youtube.com/embed/2NZMaI-HeNU",
        body_part="Neck",
        description="Gently tilt your head toward one shoulder, hold 15-30 seconds, then switch sides.",
    ),
    "neck_rotation": _res(
        id="neck_rotation",
        title="Neck Rotation Stretch",
        youtube_embed_url="https://www.youtube.com/embed/wQylqaCl8Zo",
        body_part="Neck",
        description="Slowly turn your head to one side until you feel a stretch, hold 15-30 seconds, then switch.",
    ),
    "upper_trap_stretch": _res(
        id="upper_trap_stretch",
        title="Upper Trapezius Stretch",
        youtube_embed_url="https://www.youtube.com/embed/2NZMaI-HeNU",
        body_part="Neck / Shoulder",
        description="Tilt head away from tight side while gently pressing down with opposite hand. Hold 20-30 seconds.",
    ),
    "shoulder_cross_body": _res(
        id="shoulder_cross_body",
        title="Shoulder Cross-Body Stretch",
        youtube_embed_url="https://www.youtube.com/embed/Rl4Zudadpc8",
        body_part="Shoulder",
        description="Bring one arm across your chest, use the opposite hand to press gently. Hold 20-30 seconds.",
    ),
    "shoulder_overhead": _res(
        id="shoulder_overhead",
        title="Overhead Shoulder Stretch",
        youtube_embed_url="https://www.youtube.com/embed/es0Nh_XlWOg",
        body_part="Shoulder / Lat",
        description="Reach one arm overhead and bend elbow behind your head. Use other hand to gently pull. Hold 20-30 seconds.",
    ),
    "chest_opener": _res(
        id="chest_opener",
        title="Chest Opener Stretch",
        youtube_embed_url="https://www.youtube.com/embed/SxQkGMuYNEA",
        body_part="Chest",
        description="Clasp hands behind your back, straighten arms and lift gently while opening chest. Hold 20-30 seconds.",
    ),
    "bicep_stretch": _res(
        id="bicep_stretch",
        title="Bicep Wall Stretch",
        youtube_embed_url="https://www.youtube.com/embed/iSx_0xJMGi4",
        body_part="Arm",
        description="Place palm flat against wall at shoulder height, slowly rotate body away. Hold 20-30 seconds per arm.",
    ),
    "tricep_stretch": _res(
        id="tricep_stretch",
        title="Tricep Stretch",
        youtube_embed_url="https://www.youtube.com/embed/es0Nh_XlWOg",
        body_part="Arm",
        description="Reach one hand behind your head, use other hand to gently press elbow back. Hold 20-30 seconds.",
    ),
    "wrist_flexor_stretch": _res(
        id="wrist_flexor_stretch",
        title="Wrist Flexor Stretch",
        youtube_embed_url="https://www.youtube.com/embed/u4w0Y5NQFLY",
        body_part="Arm / Wrist",
        description="Extend arm, palm up. Use other hand to gently press fingers back toward you. Hold 15-20 seconds.",
    ),
    "cat_cow": _res(
        id="cat_cow",
        title="Cat-Cow Stretch",
        youtube_embed_url="https://www.youtube.com/embed/kqnua4rHVVA",
        body_part="Spine",
        description="On all fours, alternate between arching your back (cow) and rounding it (cat). 10-15 reps.",
    ),
}


def get_resource(stretch_id: str) -> ExerciseResource | None:
    """Look up a static exercise resource by ID."""
    return EXERCISE_RESOURCES.get(stretch_id)


def search_static_resources(query: str) -> ExerciseResource | None:
    """Fuzzy search static resources by title or body part."""
    query_lower = query.lower()
    for resource in EXERCISE_RESOURCES.values():
        if query_lower in resource.title.lower() or query_lower in resource.body_part.lower():
            return resource
    for resource in EXERCISE_RESOURCES.values():
        if any(word in resource.title.lower() for word in query_lower.split()):
            return resource
    return None


def list_resource_ids() -> list[str]:
    """Return all available stretch IDs."""
    return list(EXERCISE_RESOURCES.keys())
