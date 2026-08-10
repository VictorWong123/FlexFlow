from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import time
from types import SimpleNamespace
import pytest

from app.coach import PROTOCOLS, Observation, SessionCoach, catalog_tracking, find_protocol
from app.pain_guardrail import check_pain_keywords, claim_pain_event, should_handle_pain_transcript
from app.state import AsyncState
from app.utils.physics import angle_degrees_3d
from app.vision import extract_pose_metrics
from app import vision
from app.agent import FlexFlowAgent


def observe(timestamp_ms: int, value: float, *, view: str = "side", confidence: float = 0.9, issues: tuple[str, ...] = ()) -> Observation:
    return Observation(
        timestamp_ms=timestamp_ms,
        confidence=confidence,
        metrics={"knee_flexion": value},
        visibility={"knee_flexion": confidence},
        view=view,  # type: ignore[arg-type]
        issues=issues,
    )


def settle(coach: SessionCoach, start_ms: int, value: float, **kwargs: object) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for offset in (0, 125, 250):
        snapshot = coach.observe(observe(start_ms + offset, value, **kwargs))
    return snapshot


def test_aliases_and_unsupported_catalog() -> None:
    assert {protocol.id for protocol in PROTOCOLS} == {
        "neck-lateral-hold",
        "shoulder-abduction",
        "shoulder-flexion",
        "elbow-flexion",
        "overhead-press",
        "squat",
        "split-squat-lunge",
        "hip-hinge",
        "standing-knee-flexion",
        "calf-raise",
    }
    assert find_protocol("Dumbbell lateral raise").id == "shoulder-abduction"  # type: ignore[union-attr]
    assert find_protocol("Romanian deadlift").id == "hip-hinge"  # type: ignore[union-attr]
    assert find_protocol("not an exercise") is None
    assert catalog_tracking("not an exercise") == {
        "canonical_id": None,
        "tracking_supported": False,
        "required_view": None,
        "calibration_required": False,
    }


def test_rep_requires_start_end_start_with_frame_and_time_dwell() -> None:
    coach = SessionCoach()
    coach.activate("bodyweight squat")

    coach.observe(observe(0, 170))
    coach.observe(observe(100, 170))
    assert coach.observe(observe(200, 170))["status"] == "calibrating"  # three frames, not 250 ms
    assert settle(coach, 250, 170)["status"] == "tracking"
    assert settle(coach, 600, 90)["reps"] == 0
    assert settle(coach, 950, 170)["reps"] == 1


@pytest.mark.parametrize("protocol", [protocol for protocol in PROTOCOLS if not protocol.hold], ids=lambda protocol: protocol.id)
def test_all_rep_protocols_count_full_cycle(protocol) -> None:
    coach = SessionCoach()
    coach.activate(protocol.aliases[0])

    def reading(timestamp: int, bounds: tuple[float, float]) -> Observation:
        return Observation(
            timestamp_ms=timestamp,
            confidence=0.9,
            metrics={protocol.metric: sum(bounds) / 2},
            visibility={protocol.metric: 0.9},
            view=protocol.required_view,
        )

    for base, bounds in ((0, protocol.start), (350, protocol.end), (700, protocol.start)):
        for offset in (0, 125, 250):
            snapshot = coach.observe(reading(base + offset, bounds))
    assert snapshot["reps"] == 1


def test_hold_protocol_tracks_elapsed_hold() -> None:
    protocol = next(protocol for protocol in PROTOCOLS if protocol.hold)
    coach = SessionCoach()
    coach.activate(protocol.aliases[0])

    def reading(timestamp: int, bounds: tuple[float, float]) -> Observation:
        return Observation(timestamp, 0.9, {protocol.metric: sum(bounds) / 2}, protocol.required_view, {protocol.metric: 0.9})

    for base, bounds in ((0, protocol.start), (350, protocol.end)):
        for offset in (0, 125, 250):
            coach.observe(reading(base + offset, bounds))
    assert coach.observe(reading(1_600, protocol.end))["hold_seconds"] == 1


def test_visibility_view_and_stale_gate_tracking() -> None:
    coach = SessionCoach()
    coach.activate("squat")
    assert coach.observe(observe(0, 170, confidence=0.2))["status"] == "lost_visibility"
    assert coach.observe(observe(10, 170, view="front"))["status"] == "wrong_view"
    settle(coach, 100, 170)
    assert coach.snapshot(851)["status"] == "stale"


def test_halt_resume_recalibrates_before_a_rep() -> None:
    coach = SessionCoach()
    coach.activate("squat")
    settle(coach, 0, 170)
    settle(coach, 350, 90)
    coach.halt()
    assert coach.observe(observe(700, 170))["status"] == "halted"
    coach.resume()
    assert coach.snapshot(700)["status"] == "calibrating"
    assert settle(coach, 750, 170)["reps"] == 0


def test_hold_and_persistent_cue_cooldown() -> None:
    coach = SessionCoach()
    coach.activate("neck lateral hold")
    neck = lambda timestamp, value, **kwargs: Observation(
        timestamp_ms=timestamp,
        confidence=0.9,
        metrics={"neck_tilt": value},
        visibility={"neck_tilt": 0.9},
        view="front",
        **kwargs,
    )
    for timestamp in (0, 125, 250):
        coach.observe(neck(timestamp, 0))
    for timestamp in (350, 475, 600):
        coach.observe(neck(timestamp, 25))
    assert coach.observe(neck(1_600, 25))["hold_seconds"] == 1

    assert coach.observe(neck(2_000, 25, issues=("Relax your shoulder.",)))["cue"] is None
    assert coach.observe(neck(2_750, 25, issues=("Relax your shoulder.",)))["cue"] == "Relax your shoulder."
    assert coach.observe(neck(2_800, 25))["cue"] is None
    assert coach.observe(neck(3_000, 25, issues=("Relax your shoulder.",)))["cue"] is None
    assert coach.observe(neck(7_800, 25, issues=("Relax your shoulder.",)))["cue"] == "Relax your shoulder."


def test_async_state_isolated_per_session() -> None:
    async def check() -> None:
        first, second = AsyncState(), AsyncState()
        await first.activate_exercise("squat")
        assert (await first.snapshot())["tracking"]["protocol_id"] == "squat"
        assert (await second.snapshot())["tracking"]["status"] == "unsupported"

    asyncio.run(check())


def test_pain_word_boundaries_and_dedupe() -> None:
    handled: set[str] = set()
    assert check_pain_keywords("My knee hurts!")
    assert not check_pain_keywords("I am stopping by later")
    assert claim_pain_event("My knee hurts!", handled)
    assert not claim_pain_event("my knee hurts", handled)
    assert should_handle_pain_transcript("stop", is_final=False)
    assert should_handle_pain_transcript("ouch!", is_final=False)
    assert not should_handle_pain_transcript("stopping", is_final=False)
    assert not should_handle_pain_transcript("my knee hurts", is_final=False)
    assert should_handle_pain_transcript("my knee hurts", is_final=True)


@dataclass
class Landmark:
    x: float = 0.5
    y: float = 0.5
    z: float = 0.0
    visibility: float = 0.9


def test_synthetic_landmarks_produce_metric_visibility_and_side_view() -> None:
    landmarks = [Landmark() for _ in range(33)]
    landmarks[0] = Landmark(0.5, 0.2)
    landmarks[11] = Landmark(0.4, 0.5, -0.2)
    landmarks[12] = Landmark(0.6, 0.5, 0.2)
    landmarks[13] = Landmark(0.4, 0.7)
    landmarks[15] = Landmark(0.6, 0.7)
    landmarks[23] = Landmark(0.4, 0.8, -0.1)
    landmarks[25] = Landmark(0.4, 0.9)
    landmarks[27] = Landmark(0.5, 1.0)
    landmarks[31] = Landmark(0.6, 1.0)

    result = extract_pose_metrics(landmarks)
    assert result["view"] == "side"
    assert result["confidence"] == 0.9
    assert result["visibility"]["knee_flexion"] == 0.9
    assert "knee_flexion" in result["metrics"]
    assert round(angle_degrees_3d((1, 0, 0), (0, 0, 0), (0, 1, 0))) == 90


def test_landmark_extraction_bounds_front_upper_covered_and_pointing() -> None:
    with pytest.raises(ValueError, match="33"):
        extract_pose_metrics([Landmark()] * 32)

    covered = [Landmark(visibility=0.0) for _ in range(33)]
    assert extract_pose_metrics(covered) == {"camera_covered": True}

    front = [Landmark() for _ in range(33)]
    for index in range(25, 33):
        front[index].visibility = 0.2
    front[19] = Landmark(front[11].x, front[11].y, visibility=0.9)
    result = extract_pose_metrics(front)
    assert result["view"] == "front"
    assert result["is_upper_body_only"] is True
    assert result["pointed_body_part"] == "Left Shoulder"
    assert len(result["landmarks"]) == 33
    assert all(set(item) == {"x", "y", "z", "v"} for item in result["landmarks"])


def test_gemini_metrics_tool_returns_same_tracking_snapshot_as_session_coach() -> None:
    async def check() -> None:
        state = AsyncState()
        await state.activate_exercise("squat")
        timestamp = time.monotonic_ns() // 1_000_000
        latest = await state.observe(Observation(
            timestamp_ms=timestamp,
            confidence=0.9,
            metrics={"knee_flexion": 170.0},
            visibility={"knee_flexion": 0.9},
            view="side",
        ))
        room = SimpleNamespace(local_participant=SimpleNamespace())
        agent = FlexFlowAgent(state, room)
        metrics = await FlexFlowAgent.get_body_metrics._func(agent, None)  # type: ignore[arg-type]
        assert metrics["tracking"] == latest

    asyncio.run(check())


def test_vision_manager_fake_stream_updates_state_and_publishes_packet(monkeypatch) -> None:
    class Participant:
        def __init__(self) -> None:
            self.packets: list[tuple[str, bytes]] = []

        async def publish_data(self, payload: bytes, *, topic: str, **_kwargs: object) -> None:
            self.packets.append((topic, payload))

    class Frame:
        width = 2
        height = 2
        data = bytes(12)

    class Stream:
        def __init__(self, _track: object, **_kwargs: object) -> None:
            pass

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(frame=Frame(), timestamp_us=1_000)
            return events()

    async def check() -> None:
        state = AsyncState()
        await state.activate_exercise("squat")
        participant = Participant()
        manager = object.__new__(vision.VisionManager)
        manager._track = object()
        manager._state = state
        manager._local_participant = participant
        manager._running = False
        manager._closed = False
        manager._executor = ThreadPoolExecutor(max_workers=1)
        manager._landmarker = SimpleNamespace(close=lambda: None)
        manager._neck_buf = deque(maxlen=5)
        manager._left_elbow_buf = deque(maxlen=5)
        manager._right_elbow_buf = deque(maxlen=5)
        manager._last_publish = 0.0
        manager._last_tracking_publish = 0.0
        manager._last_tracking_payload = None
        manager._last_tracking_state = None

        def process(_rgb: object, _timestamp: int) -> dict[str, object]:
            manager._running = False
            return {
                "is_upper_body_only": False,
                "neck_angle": 0.0,
                "left_elbow": 170.0,
                "right_elbow": 170.0,
                "pointed_body_part": "",
                "confidence": 0.9,
                "view": "side",
                "metrics": {"knee_flexion": 170.0},
                "visibility": {"knee_flexion": 0.9},
                "landmarks": [],
            }

        manager._process_frame_sync = process
        fake_rtc = SimpleNamespace(VideoStream=Stream, VideoBufferType=SimpleNamespace(RGB24=1))
        monkeypatch.setattr(vision, "rtc", fake_rtc)
        await manager.run()
        tracking_packets = [json.loads(payload) for topic, payload in participant.packets if topic == "tracking"]
        assert tracking_packets
        assert any(packet["protocol_id"] == "squat" for packet in tracking_packets)
        snapshot = await state.snapshot()
        assert snapshot["arm_angles"] == {"left_elbow": 170.0, "right_elbow": 170.0}

    asyncio.run(check())


def test_tracking_publish_caps_ordinary_updates_and_bypasses_for_reps(monkeypatch) -> None:
    class Participant:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []

        async def publish_data(self, payload: bytes, **_kwargs: object) -> None:
            self.payloads.append(payload)

    async def check() -> None:
        participant = Participant()
        manager = object.__new__(vision.VisionManager)
        manager._local_participant = participant
        manager._last_tracking_publish = 0.0
        manager._last_tracking_payload = None
        manager._last_tracking_state = None
        times = iter((1.0, 1.01, 1.02, 1.03, 1.13))
        monkeypatch.setattr(vision, "time", SimpleNamespace(monotonic=lambda: next(times)))

        await manager._publish_tracking({"status": "tracking", "reps": 0, "hold_seconds": 0, "observed_at_ms": 1})
        await manager._publish_tracking({"status": "tracking", "reps": 0, "hold_seconds": 1, "observed_at_ms": 2})
        await manager._publish_tracking({"status": "tracking", "reps": 1, "hold_seconds": 1, "observed_at_ms": 3})
        await manager._publish_tracking({"status": "tracking", "reps": 1, "hold_seconds": 2, "observed_at_ms": 4})
        await manager._publish_tracking({"status": "tracking", "reps": 1, "hold_seconds": 2, "observed_at_ms": 5})
        assert len(participant.payloads) == 3
        assert all(b"observed_at_ms" not in payload for payload in participant.payloads)

    asyncio.run(check())


def test_no_frame_heartbeat_publishes_stale_state(monkeypatch) -> None:
    class State:
        async def snapshot(self) -> dict[str, object]:
            return {"tracking": {"status": "stale", "reps": 0, "halted": False}}

    class Participant:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []

        async def publish_data(self, payload: bytes, **_kwargs: object) -> None:
            self.payloads.append(payload)

    async def check() -> None:
        manager = object.__new__(vision.VisionManager)
        manager._state = State()
        manager._local_participant = Participant()
        manager._last_tracking_publish = 0.0
        manager._last_tracking_payload = None
        manager._last_tracking_state = None
        monkeypatch.setattr(vision, "time", SimpleNamespace(monotonic=lambda: 1.0))
        await manager._publish_state_heartbeat()
        assert json.loads(manager._local_participant.payloads[0]) == {
            "halted": False,
            "reps": 0,
            "status": "stale",
        }

    asyncio.run(check())
