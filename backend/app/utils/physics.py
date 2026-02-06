"""
Vision math for FlexFlow: neck tilt and elbow flexion.
Use relative coordinates (0-1) and atan2 for stability.
Return "Low Confidence" when visibility < MIN_VISIBILITY_THRESHOLD.
"""

from __future__ import annotations

import math
from typing import Any

MIN_VISIBILITY_THRESHOLD = 0.6


def _visibility(landmark: Any) -> float:
    """Get visibility from a MediaPipe landmark (0-1)."""
    return getattr(landmark, "visibility", 1.0)


def _point(landmark: Any) -> tuple[float, float]:
    """(x, y) in relative coords from landmark."""
    return (float(landmark.x), float(landmark.y))


def angle_degrees_from_vectors(
    p_mid: tuple[float, float],
    p_from: tuple[float, float],
    p_to: tuple[float, float],
) -> float:
    """
    Angle at p_from between vectors (p_from -> p_mid) and (p_from -> p_to), in degrees.
    Uses atan2 for stability. Returns 0 if points are degenerate.
    """
    dx1 = p_mid[0] - p_from[0]
    dy1 = p_mid[1] - p_from[1]
    dx2 = p_to[0] - p_from[0]
    dy2 = p_to[1] - p_from[1]
    a1 = math.atan2(dy1, dx1)
    a2 = math.atan2(dy2, dx2)
    deg = math.degrees(a1 - a2)
    if deg > 180:
        deg -= 360
    elif deg < -180:
        deg += 360
    return deg


def neck_tilt_degrees(
    nose: Any,
    left_shoulder: Any,
    right_shoulder: Any,
) -> float | None:
    """
    Neck tilt: angle of nose relative to shoulder mid-point (vertical reference).
    MediaPipe pose: 0=nose, 11=left_shoulder, 12=right_shoulder.
    Returns None (Low Confidence) if any landmark visibility < MIN_VISIBILITY_THRESHOLD.
    """
    if (
        _visibility(nose) < MIN_VISIBILITY_THRESHOLD
        or _visibility(left_shoulder) < MIN_VISIBILITY_THRESHOLD
        or _visibility(right_shoulder) < MIN_VISIBILITY_THRESHOLD
    ):
        return None
    p_nose = _point(nose)
    p_ls = _point(left_shoulder)
    p_rs = _point(right_shoulder)
    mid_x = (p_ls[0] + p_rs[0]) / 2
    mid_y = (p_ls[1] + p_rs[1]) / 2
    shoulder_mid = (mid_x, mid_y)
    up = (mid_x, mid_y - 0.1)  # y decreases up in image coords
    return angle_degrees_from_vectors(up, shoulder_mid, p_nose)


def elbow_flexion_degrees(
    shoulder: Any,
    elbow: Any,
    wrist: Any,
) -> float | None:
    """
    Elbow flexion: angle at elbow between shoulder->elbow and elbow->wrist.
    MediaPipe pose: 11/12=shoulders, 13/14=elbows, 15/16=wrists.
    Returns None (Low Confidence) if any landmark visibility < MIN_VISIBILITY_THRESHOLD.
    """
    if (
        _visibility(shoulder) < MIN_VISIBILITY_THRESHOLD
        or _visibility(elbow) < MIN_VISIBILITY_THRESHOLD
        or _visibility(wrist) < MIN_VISIBILITY_THRESHOLD
    ):
        return None
    p_s = _point(shoulder)
    p_e = _point(elbow)
    p_w = _point(wrist)
    return angle_degrees_from_vectors(p_s, p_e, p_w)
