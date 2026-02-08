"""
Vision math for FlexFlow: 3D neck tilt and elbow flexion using MediaPipe pose landmarks.
All calculations use true 3D coordinates (x, y, z) for accurate joint angle measurement.
Returns None when visibility < MIN_VISIBILITY_THRESHOLD.
"""

from __future__ import annotations

import math
from typing import Any

MIN_VISIBILITY_THRESHOLD = 0.6


def _visibility(landmark: Any) -> float:
    """Get visibility from a MediaPipe landmark (0-1)."""
    return getattr(landmark, "visibility", 1.0)


def _point_3d(landmark: Any) -> tuple[float, float, float]:
    """(x, y, z) in relative coords from MediaPipe landmark."""
    return (float(landmark.x), float(landmark.y), float(landmark.z))


def angle_degrees_3d(
    p_a: tuple[float, float, float],
    p_vertex: tuple[float, float, float],
    p_c: tuple[float, float, float],
) -> float:
    """
    Calculate angle at p_vertex between vectors (vertex -> p_a) and (vertex -> p_c) in 3D.
    Uses dot product and magnitudes for true 3D angle measurement.
    Returns angle in degrees [0, 180].
    """
    v1 = (p_a[0] - p_vertex[0], p_a[1] - p_vertex[1], p_a[2] - p_vertex[2])
    v2 = (p_c[0] - p_vertex[0], p_c[1] - p_vertex[1], p_c[2] - p_vertex[2])

    dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)

    if mag1 < 1e-6 or mag2 < 1e-6:
        return 0.0

    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def neck_tilt_degrees(
    nose: Any,
    left_shoulder: Any,
    right_shoulder: Any,
) -> float | None:
    """
    Neck tilt in 3D: angle of nose relative to shoulder mid-point (vertical reference).
    MediaPipe pose: 0=nose, 11=left_shoulder, 12=right_shoulder.
    Returns None if any landmark visibility < MIN_VISIBILITY_THRESHOLD.
    """
    if (
        _visibility(nose) < MIN_VISIBILITY_THRESHOLD
        or _visibility(left_shoulder) < MIN_VISIBILITY_THRESHOLD
        or _visibility(right_shoulder) < MIN_VISIBILITY_THRESHOLD
    ):
        return None

    p_nose = _point_3d(nose)
    p_ls = _point_3d(left_shoulder)
    p_rs = _point_3d(right_shoulder)

    mid_x = (p_ls[0] + p_rs[0]) / 2
    mid_y = (p_ls[1] + p_rs[1]) / 2
    mid_z = (p_ls[2] + p_rs[2]) / 2
    shoulder_mid = (mid_x, mid_y, mid_z)

    up = (mid_x, mid_y - 0.1, mid_z)

    return angle_degrees_3d(up, shoulder_mid, p_nose)


def elbow_flexion_degrees(
    shoulder: Any,
    elbow: Any,
    wrist: Any,
) -> float | None:
    """
    Elbow flexion in 3D: angle at elbow between shoulder->elbow and elbow->wrist vectors.
    MediaPipe pose: 11/12=shoulders, 13/14=elbows, 15/16=wrists.
    Returns None if any landmark visibility < MIN_VISIBILITY_THRESHOLD.
    """
    if (
        _visibility(shoulder) < MIN_VISIBILITY_THRESHOLD
        or _visibility(elbow) < MIN_VISIBILITY_THRESHOLD
        or _visibility(wrist) < MIN_VISIBILITY_THRESHOLD
    ):
        return None

    p_s = _point_3d(shoulder)
    p_e = _point_3d(elbow)
    p_w = _point_3d(wrist)

    return angle_degrees_3d(p_s, p_e, p_w)
