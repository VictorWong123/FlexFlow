"""
VisionManager: real-time MediaPipe Pose processing on LiveKit video tracks.
Uses the MediaPipe Tasks API (PoseLandmarker) with VIDEO running mode.
Processes frames in a ThreadPoolExecutor (non-blocking), applies smoothing,
writes body metrics to AsyncState, and publishes landmark positions to the
room for frontend overlay rendering. Zero-storage; in-memory only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import mediapipe as mp
import numpy as np
from livekit import rtc

from app.state import AsyncState
from app.utils.physics import elbow_flexion_degrees, neck_tilt_degrees

logger = logging.getLogger("flexflow.vision")

_MODEL_PATH = str(Path(__file__).parent / "models" / "pose_landmarker_lite.task")

_NOSE = 0
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_ELBOW = 13
_RIGHT_ELBOW = 14
_LEFT_WRIST = 15
_RIGHT_WRIST = 16
_LEFT_INDEX = 19
_RIGHT_INDEX = 20
_LOWER_BODY = (25, 26, 27, 28, 29, 30, 31, 32)

_POINTING_TARGETS: dict[int, str] = {
    _LEFT_SHOULDER: "Left Shoulder",
    _RIGHT_SHOULDER: "Right Shoulder",
    _LEFT_ELBOW: "Left Elbow",
    _RIGHT_ELBOW: "Right Elbow",
    25: "Left Knee",
    26: "Right Knee",
}

_LOWER_VIS_THRESHOLD = 0.5
_POINTING_DIST_THRESHOLD = 0.1
_SMOOTHING_SIZE = 5
_LANDMARK_PUBLISH_INTERVAL = 0.1  # seconds (~10 fps)


class VisionManager:
    """Reads a LiveKit VideoTrack, runs PoseLandmarker off-thread, updates AsyncState."""

    def __init__(
        self,
        track: rtc.Track,
        state: AsyncState,
        local_participant: rtc.LocalParticipant,
    ) -> None:
        self._track = track
        self._state = state
        self._local_participant = local_participant
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._last_publish = 0.0

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)

        self._neck_buf: deque[float] = deque(maxlen=_SMOOTHING_SIZE)
        self._left_elbow_buf: deque[float] = deque(maxlen=_SMOOTHING_SIZE)
        self._right_elbow_buf: deque[float] = deque(maxlen=_SMOOTHING_SIZE)

    @staticmethod
    def _smooth(buf: deque[float], value: float | None) -> float:
        if value is None:
            return buf[-1] if buf else 0.0
        buf.append(value)
        return sum(buf) / len(buf)

    def _process_frame_sync(
        self, rgb: np.ndarray, timestamp_ms: int
    ) -> dict[str, Any] | None:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None

        lm = result.pose_landmarks[0]

        if all(getattr(lm[i], "visibility", 0.0) < 0.1 for i in range(33)):
            return {"camera_covered": True}

        vis = lambda idx: getattr(lm[idx], "visibility", 0.0)

        is_upper_only = all(vis(i) < _LOWER_VIS_THRESHOLD for i in _LOWER_BODY)

        pointed = ""
        for finger_idx in (_LEFT_INDEX, _RIGHT_INDEX):
            if vis(finger_idx) < _LOWER_VIS_THRESHOLD:
                continue
            fx, fy = lm[finger_idx].x, lm[finger_idx].y
            min_dist = float("inf")
            closest = ""
            for target_idx, label in _POINTING_TARGETS.items():
                if vis(target_idx) < _LOWER_VIS_THRESHOLD:
                    continue
                dist = math.sqrt(
                    (fx - lm[target_idx].x) ** 2 + (fy - lm[target_idx].y) ** 2
                )
                if dist < _POINTING_DIST_THRESHOLD and dist < min_dist:
                    min_dist = dist
                    closest = label
            if closest:
                pointed = closest
                break

        neck = neck_tilt_degrees(lm[_NOSE], lm[_LEFT_SHOULDER], lm[_RIGHT_SHOULDER])
        left_elbow = elbow_flexion_degrees(
            lm[_LEFT_SHOULDER], lm[_LEFT_ELBOW], lm[_LEFT_WRIST]
        )
        right_elbow = elbow_flexion_degrees(
            lm[_RIGHT_SHOULDER], lm[_RIGHT_ELBOW], lm[_RIGHT_WRIST]
        )

        landmarks = [
            {
                "x": round(lm[i].x, 4),
                "y": round(lm[i].y, 4),
                "z": round(lm[i].z, 4),
                "v": round(vis(i), 2),
            }
            for i in range(33)
        ]

        return {
            "is_upper_body_only": is_upper_only,
            "neck_angle": neck,
            "left_elbow": left_elbow,
            "right_elbow": right_elbow,
            "pointed_body_part": pointed,
            "landmarks": landmarks,
        }

    async def _publish_landmarks(self, landmarks: list[dict[str, float]]) -> None:
        now = time.monotonic()
        if now - self._last_publish < _LANDMARK_PUBLISH_INTERVAL:
            return
        self._last_publish = now
        try:
            payload = json.dumps({"l": landmarks}).encode("utf-8")
            await self._local_participant.publish_data(
                payload, reliable=False, topic="landmarks"
            )
        except Exception:
            pass

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_event_loop()
        video_stream = rtc.VideoStream(
            self._track, format=rtc.VideoBufferType.RGB24
        )

        latest: tuple[np.ndarray, int] | None = None

        async def _read_frames() -> None:
            nonlocal latest
            async for event in video_stream:
                if not self._running:
                    break
                buf = event.frame
                arr = np.frombuffer(buf.data, dtype=np.uint8)
                frame = arr.reshape((buf.height, buf.width, 3)).copy()
                ts_ms = event.timestamp_us // 1000
                latest = (frame, ts_ms)

        reader = asyncio.create_task(_read_frames())

        try:
            while self._running:
                if latest is None:
                    await asyncio.sleep(0.05)
                    continue

                frame, ts_ms = latest
                latest = None

                result = await loop.run_in_executor(
                    self._executor, self._process_frame_sync, frame, ts_ms
                )

                if result is None:
                    continue

                if result.get("camera_covered"):
                    await self._state.update(
                        is_upper_body_only=True, pointed_body_part=""
                    )
                    continue

                neck_s = self._smooth(self._neck_buf, result["neck_angle"])
                left_s = self._smooth(self._left_elbow_buf, result["left_elbow"])
                right_s = self._smooth(self._right_elbow_buf, result["right_elbow"])

                await self._state.update(
                    is_upper_body_only=result["is_upper_body_only"],
                    neck_angle=round(neck_s, 1),
                    arm_angles={
                        "left_elbow": round(left_s, 1),
                        "right_elbow": round(right_s, 1),
                    },
                    pointed_body_part=result["pointed_body_part"],
                )

                if result.get("landmarks"):
                    await self._publish_landmarks(result["landmarks"])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Vision loop error")
        finally:
            reader.cancel()
            await self.close()

    async def close(self) -> None:
        self._running = False
        self._landmarker.close()
        self._executor.shutdown(wait=False)
