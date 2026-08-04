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
from contextlib import suppress
from typing import Any, Sequence

import numpy as np

try:  # Keep deterministic metric helpers importable in lightweight test environments.
    import mediapipe as mp
    from livekit import rtc
except ImportError:  # pragma: no cover - production installs both runtime dependencies.
    mp = None
    rtc = None

from app.coach import MIN_CONFIDENCE, Observation
from app.state import AsyncState
from app.utils.physics import angle_degrees_3d, elbow_flexion_degrees, neck_tilt_degrees

logger = logging.getLogger("flexflow.vision")

_MODEL_PATH = str(Path(__file__).parent / "models" / "pose_landmarker_lite.task")

_NOSE = 0
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_ELBOW = 13
_RIGHT_ELBOW = 14
_LEFT_WRIST = 15
_RIGHT_WRIST = 16
_LEFT_HIP = 23
_RIGHT_HIP = 24
_LEFT_KNEE = 25
_RIGHT_KNEE = 26
_LEFT_ANKLE = 27
_RIGHT_ANKLE = 28
_LEFT_FOOT = 31
_RIGHT_FOOT = 32
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
_TRACKING_PUBLISH_INTERVAL = 0.1


def extract_pose_metrics(lm: Sequence[Any]) -> dict[str, Any]:
    """Convert one MediaPipe pose to deterministic metrics and camera metadata."""
    if len(lm) < 33:
        raise ValueError("Pose landmark list must contain 33 landmarks.")

    visibility = lambda index: float(getattr(lm[index], "visibility", 0.0))
    if all(visibility(index) < 0.1 for index in range(33)):
        return {"camera_covered": True}

    is_upper_only = all(visibility(index) < _LOWER_VIS_THRESHOLD for index in _LOWER_BODY)
    pointed = ""
    for finger_index in (_LEFT_INDEX, _RIGHT_INDEX):
        if visibility(finger_index) < _LOWER_VIS_THRESHOLD:
            continue
        finger_x, finger_y = lm[finger_index].x, lm[finger_index].y
        closest = ""
        closest_distance = float("inf")
        for target_index, label in _POINTING_TARGETS.items():
            if visibility(target_index) < _LOWER_VIS_THRESHOLD:
                continue
            distance = math.hypot(finger_x - lm[target_index].x, finger_y - lm[target_index].y)
            if distance < _POINTING_DIST_THRESHOLD and distance < closest_distance:
                closest_distance, closest = distance, label
        if closest:
            pointed = closest
            break

    def joint_angle(a: int, vertex: int, c: int) -> float | None:
        if min(visibility(a), visibility(vertex), visibility(c)) < MIN_CONFIDENCE:
            return None
        point = lambda index: (float(lm[index].x), float(lm[index].y), float(lm[index].z))
        return angle_degrees_3d(point(a), point(vertex), point(c))

    left_side_visibility = sum(visibility(index) for index in (_LEFT_SHOULDER, _LEFT_HIP, _LEFT_KNEE, _LEFT_ANKLE))
    right_side_visibility = sum(visibility(index) for index in (_RIGHT_SHOULDER, _RIGHT_HIP, _RIGHT_KNEE, _RIGHT_ANKLE))
    shoulder, elbow, wrist, hip, knee, ankle, foot = (
        (_LEFT_SHOULDER, _LEFT_ELBOW, _LEFT_WRIST, _LEFT_HIP, _LEFT_KNEE, _LEFT_ANKLE, _LEFT_FOOT)
        if left_side_visibility >= right_side_visibility
        else (_RIGHT_SHOULDER, _RIGHT_ELBOW, _RIGHT_WRIST, _RIGHT_HIP, _RIGHT_KNEE, _RIGHT_ANKLE, _RIGHT_FOOT)
    )
    neck = neck_tilt_degrees(lm[_NOSE], lm[_LEFT_SHOULDER], lm[_RIGHT_SHOULDER])
    left_elbow = elbow_flexion_degrees(lm[_LEFT_SHOULDER], lm[_LEFT_ELBOW], lm[_LEFT_WRIST])
    right_elbow = elbow_flexion_degrees(lm[_RIGHT_SHOULDER], lm[_RIGHT_ELBOW], lm[_RIGHT_WRIST])
    shoulder_angle = joint_angle(hip, shoulder, elbow)
    metrics = {
        "neck_tilt": neck,
        "shoulder_abduction": shoulder_angle,
        "shoulder_flexion": shoulder_angle,
        "elbow_flexion": joint_angle(shoulder, elbow, wrist),
        "knee_flexion": joint_angle(hip, knee, ankle),
        "hip_flexion": joint_angle(shoulder, hip, knee),
        "ankle_flexion": joint_angle(knee, ankle, foot),
    }
    metric_visibility = {
        "neck_tilt": min(visibility(_NOSE), visibility(_LEFT_SHOULDER), visibility(_RIGHT_SHOULDER)),
        "shoulder_abduction": min(visibility(hip), visibility(shoulder), visibility(elbow)),
        "shoulder_flexion": min(visibility(hip), visibility(shoulder), visibility(elbow)),
        "elbow_flexion": min(visibility(shoulder), visibility(elbow), visibility(wrist)),
        "knee_flexion": min(visibility(hip), visibility(knee), visibility(ankle)),
        "hip_flexion": min(visibility(shoulder), visibility(hip), visibility(knee)),
        "ankle_flexion": min(visibility(knee), visibility(ankle), visibility(foot)),
    }
    shoulder_depth = abs(float(lm[_LEFT_SHOULDER].z) - float(lm[_RIGHT_SHOULDER].z))
    hip_depth = abs(float(lm[_LEFT_HIP].z) - float(lm[_RIGHT_HIP].z))
    return {
        "is_upper_body_only": is_upper_only,
        "neck_angle": neck,
        "left_elbow": left_elbow,
        "right_elbow": right_elbow,
        "pointed_body_part": pointed,
        "confidence": max(metric_visibility.values(), default=0.0),
        "view": "side" if max(shoulder_depth, hip_depth) > 0.12 else "front",
        "metrics": {name: value for name, value in metrics.items() if value is not None},
        "visibility": metric_visibility,
        "landmarks": [
            {"x": round(lm[index].x, 4), "y": round(lm[index].y, 4), "z": round(lm[index].z, 4), "v": round(visibility(index), 2)}
            for index in range(33)
        ],
    }


class VisionManager:
    """Reads a LiveKit VideoTrack, runs PoseLandmarker off-thread, updates AsyncState."""

    def __init__(
        self,
        track: rtc.Track,
        state: AsyncState,
        local_participant: rtc.LocalParticipant,
    ) -> None:
        if mp is None or rtc is None:
            raise RuntimeError("VisionManager requires mediapipe and livekit runtime dependencies.")
        self._track = track
        self._state = state
        self._local_participant = local_participant
        self._running = False
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._last_publish = 0.0
        self._last_tracking_publish = 0.0
        self._last_tracking_payload: bytes | None = None
        self._last_tracking_state: dict[str, object] | None = None
        self._last_landmarker_timestamp_ms = -1

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
        timestamp_ms = max(timestamp_ms, self._last_landmarker_timestamp_ms + 1)
        self._last_landmarker_timestamp_ms = timestamp_ms
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None
        return extract_pose_metrics(result.pose_landmarks[0])

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

    async def _publish_tracking(self, tracking: dict[str, object]) -> None:
        payload = json.dumps(
            {key: value for key, value in tracking.items() if key != "observed_at_ms"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        now = time.monotonic()
        previous = self._last_tracking_state
        urgent = previous is None or (
            tracking.get("halted") is True and previous.get("halted") is not True
        ) or (
            tracking.get("status") != previous.get("status")
            and tracking.get("status") in {"halted", "lost_visibility", "stale", "wrong_view"}
        ) or (
            tracking.get("cue") is not None and tracking.get("cue") != previous.get("cue")
        ) or tracking.get("reps") != previous.get("reps")
        if not urgent and now - self._last_tracking_publish < _TRACKING_PUBLISH_INTERVAL:
            return
        try:
            await self._local_participant.publish_data(
                payload, reliable=False, topic="tracking"
            )
            self._last_tracking_payload = payload
            self._last_tracking_state = dict(tracking)
            self._last_tracking_publish = now
        except Exception:
            logger.debug("Tracking publish failed", exc_info=True)

    async def _publish_state_heartbeat(self) -> None:
        snapshot = await self._state.snapshot()
        tracking = snapshot.get("tracking")
        if isinstance(tracking, dict):
            await self._publish_tracking(tracking)

    async def run(self) -> None:
        if self._closed:
            return
        self._running = True
        loop = asyncio.get_running_loop()
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
                    await self._publish_state_heartbeat()
                    await asyncio.sleep(0.05)
                    continue

                frame, ts_ms = latest
                latest = None

                result = await loop.run_in_executor(
                    self._executor, self._process_frame_sync, frame, ts_ms
                )

                if result is None:
                    await self._publish_tracking(await self._state.observe(Observation(
                        timestamp_ms=time.monotonic_ns() // 1_000_000,
                        confidence=0.0,
                        metrics={},
                        view="unknown",
                    )))
                    continue

                if result.get("camera_covered"):
                    await self._state.update(
                        is_upper_body_only=True, pointed_body_part=""
                    )
                    await self._publish_tracking(await self._state.observe(Observation(
                        timestamp_ms=time.monotonic_ns() // 1_000_000,
                        confidence=0.0,
                        metrics={},
                        view="unknown",
                    )))
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

                tracking = await self._state.observe(Observation(
                    timestamp_ms=time.monotonic_ns() // 1_000_000,
                    confidence=result["confidence"],
                    metrics=result["metrics"],
                    view=result["view"],
                    visibility=result["visibility"],
                ))
                await self._publish_tracking(tracking)

                if result.get("landmarks"):
                    await self._publish_landmarks(result["landmarks"])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Vision loop error")
        finally:
            reader.cancel()
            with suppress(asyncio.CancelledError):
                await reader
            await self.close()

    async def close(self) -> None:
        """Release MediaPipe and worker exactly once; safe from cancellation cleanup."""
        if self._closed:
            return
        self._closed = True
        self._running = False
        with suppress(Exception):
            self._landmarker.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
