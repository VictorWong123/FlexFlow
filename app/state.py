"""
Shared state (Whiteboard) for FlexFlow real-time PT session.
Holds vision-derived metrics and mode; all processing is in-memory.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr


class AsyncState(BaseModel):
    """
    Real-time body metrics and session mode shared between
    the vision loop and the Gemini agent. Thread-safe via asyncio.Lock.
    """

    is_upper_body_only: bool = Field(
        default=True,
        description="True when leg landmarks (25-32) visibility < 0.5.",
    )
    neck_angle: float = Field(
        default=0.0,
        description="Neck tilt in degrees (nose relative to shoulder mid-point).",
    )
    arm_angles: dict[str, float] = Field(
        default_factory=lambda: {"left_elbow": 0.0, "right_elbow": 0.0},
        description="Elbow flexion in degrees per arm.",
    )
    pointed_body_part: str = Field(
        default="",
        description="Body part the user is pointing at or focusing on.",
    )

    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def update(
        self,
        *,
        is_upper_body_only: bool | None = None,
        neck_angle: float | None = None,
        arm_angles: dict[str, float] | None = None,
        pointed_body_part: str | None = None,
    ) -> None:
        """Update state fields under lock."""
        async with self._lock:
            if is_upper_body_only is not None:
                self.is_upper_body_only = is_upper_body_only
            if neck_angle is not None:
                self.neck_angle = neck_angle
            if arm_angles is not None:
                self.arm_angles = arm_angles
            if pointed_body_part is not None:
                self.pointed_body_part = pointed_body_part

    async def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of current state for tools (e.g. get_body_metrics)."""
        async with self._lock:
            return {
                "is_upper_body_only": self.is_upper_body_only,
                "neck_angle": self.neck_angle,
                "arm_angles": dict(self.arm_angles),
                "pointed_body_part": self.pointed_body_part or "(none)",
            }
