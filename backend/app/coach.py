"""Deterministic movement protocols and per-session tracking state."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal, Mapping

MIN_CONFIDENCE = 0.65
STALE_MS = 500
PHASE_DWELL_MS = 250
PHASE_DWELL_FRAMES = 3
ISSUE_PERSISTENCE_MS = 750
CUE_COOLDOWN_MS = 5_000

CameraView = Literal["front", "side", "unknown"]


@dataclass(frozen=True)
class Observation:
    """One timestamped, deterministic pose reading from MediaPipe."""

    timestamp_ms: int
    confidence: float
    metrics: Mapping[str, float]
    view: CameraView
    visibility: Mapping[str, float] = field(default_factory=dict)
    issues: tuple[str, ...] = ()

    def metric_is_visible(self, metric: str) -> bool:
        return self.visibility.get(metric, self.confidence) >= MIN_CONFIDENCE


@dataclass(frozen=True)
class Protocol:
    id: str
    aliases: tuple[str, ...]
    metric: str
    start: tuple[float, float]
    end: tuple[float, float]
    required_view: CameraView
    hold: bool = False


PROTOCOLS = (
    Protocol("neck-lateral-hold", ("neck lateral hold", "side neck stretch", "neck lateral flexion"), "neck_tilt", (0, 8), (18, 50), "front", True),
    Protocol("shoulder-abduction", ("side lateral raise", "shoulder abduction", "lateral raise"), "shoulder_abduction", (0, 35), (70, 125), "front"),
    Protocol("shoulder-flexion", ("front raise", "shoulder flexion"), "shoulder_flexion", (0, 35), (70, 150), "side"),
    Protocol("elbow-flexion", ("biceps curl", "elbow flexion", "barbell curl", "dumbbell curl"), "elbow_flexion", (145, 180), (35, 100), "front"),
    Protocol("overhead-press", ("shoulder press", "overhead press", "military press"), "shoulder_abduction", (20, 75), (135, 180), "front"),
    Protocol("squat", ("squat",), "knee_flexion", (150, 180), (65, 125), "side"),
    Protocol("split-squat-lunge", ("split squat", "lunge"), "knee_flexion", (150, 180), (65, 125), "side"),
    Protocol("hip-hinge", ("romanian deadlift", "hip hinge", "stiff leg deadlift"), "hip_flexion", (150, 180), (65, 125), "side"),
    Protocol("standing-knee-flexion", ("standing leg curl", "standing knee flexion"), "knee_flexion", (150, 180), (45, 115), "side"),
    Protocol("calf-raise", ("standing calf raise", "calf raise"), "ankle_flexion", (65, 105), (105, 160), "side"),
)


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def find_protocol(exercise_name: str) -> Protocol | None:
    name = _normalize(exercise_name)
    matches = [protocol for protocol in PROTOCOLS if any(alias in name for alias in protocol.aliases)]
    return max(matches, key=lambda protocol: max(map(len, protocol.aliases)), default=None)


def catalog_tracking(exercise_name: str) -> dict[str, object]:
    protocol = find_protocol(exercise_name)
    return {
        "canonical_id": protocol.id if protocol else None,
        "tracking_supported": protocol is not None,
        "required_view": protocol.required_view if protocol else None,
        "calibration_required": protocol is not None,
    }


@dataclass
class SessionCoach:
    protocol: Protocol | None = None
    reps: int = 0
    halted: bool = False
    _phase: str = "awaiting_start"
    _calibrated: bool = False
    _candidate: str | None = None
    _candidate_since: int = 0
    _candidate_frames: int = 0
    _hold_started: int | None = None
    _last_observation: Observation | None = None
    _issue_since: dict[str, int] = field(default_factory=dict)
    _last_cue: dict[str, int] = field(default_factory=dict)
    _issues: tuple[str, ...] = ()
    _cue: str | None = None

    def _reset_motion(self, *, clear_reps: bool) -> None:
        if clear_reps:
            self.reps = 0
        self._phase = "awaiting_start"
        self._calibrated = False
        self._candidate = None
        self._candidate_since = 0
        self._candidate_frames = 0
        self._hold_started = None

    def activate(self, exercise_name: str) -> None:
        protocol = find_protocol(exercise_name)
        if protocol != self.protocol:
            self.protocol = protocol
            self._reset_motion(clear_reps=True)
            self._issue_since.clear()
            self._last_cue.clear()
            self._issues = ()
            self._cue = None
            self._last_observation = None

    def halt(self) -> None:
        self.halted = True

    def resume(self) -> None:
        """Explicit resume is required after safety halt; recalibrate before counting."""
        self.halted = False
        self._reset_motion(clear_reps=False)
        self._issues = ()
        self._cue = None

    @staticmethod
    def _in_range(value: float, bounds: tuple[float, float]) -> bool:
        return bounds[0] <= value <= bounds[1]

    def _record_issues(self, issues: tuple[str, ...], timestamp_ms: int) -> None:
        active = tuple(dict.fromkeys(issue.strip() for issue in issues if issue.strip()))
        active_set = set(active)
        for issue in tuple(self._issue_since):
            if issue not in active_set:
                self._issue_since.pop(issue, None)
                self._cue = None if self._cue == issue else self._cue
        for issue in active:
            self._issue_since.setdefault(issue, timestamp_ms)
            if timestamp_ms - self._issue_since[issue] < ISSUE_PERSISTENCE_MS:
                continue
            if timestamp_ms - self._last_cue.get(issue, -CUE_COOLDOWN_MS) >= CUE_COOLDOWN_MS:
                self._last_cue[issue] = timestamp_ms
                self._cue = issue
        self._issues = active

    def _tracking_issue(self, observation: Observation, protocol: Protocol) -> str | None:
        if observation.confidence < MIN_CONFIDENCE or not observation.metric_is_visible(protocol.metric):
            return "Move fully into camera view."
        if observation.view != protocol.required_view:
            return f"Turn to a {protocol.required_view} camera view."
        if protocol.metric not in observation.metrics:
            return f"Keep {protocol.metric.replace('_', ' ')} visible."
        return None

    def observe(self, observation: Observation) -> dict[str, object]:
        self._last_observation = observation
        protocol = self.protocol
        if self.halted or protocol is None:
            self._record_issues((), observation.timestamp_ms)
            return self.snapshot(observation.timestamp_ms)

        tracking_issue = self._tracking_issue(observation, protocol)
        self._record_issues(
            observation.issues + ((tracking_issue,) if tracking_issue else ()), observation.timestamp_ms
        )
        if tracking_issue:
            self._candidate = None
            self._candidate_frames = 0
            return self.snapshot(observation.timestamp_ms)

        value = observation.metrics[protocol.metric]
        target = "end" if self._in_range(value, protocol.end) else "start" if self._in_range(value, protocol.start) else None
        if target != self._candidate:
            self._candidate, self._candidate_since, self._candidate_frames = target, observation.timestamp_ms, 1
        elif target is not None:
            self._candidate_frames += 1

        stable = bool(target) and self._candidate_frames >= PHASE_DWELL_FRAMES and observation.timestamp_ms - self._candidate_since >= PHASE_DWELL_MS
        if stable and target == "start" and self._phase == "awaiting_start":
            self._phase = "start"
            self._calibrated = True
        elif stable and target == "end" and self._phase == "start":
            self._phase = "end"
            self._hold_started = observation.timestamp_ms if protocol.hold else None
        elif stable and target == "start" and self._phase == "end":
            self.reps += 1
            self._phase = "start"
            self._hold_started = None

        return self.snapshot(observation.timestamp_ms)

    def snapshot(self, now_ms: int) -> dict[str, object]:
        observation = self._last_observation
        protocol = self.protocol
        if self.halted:
            status = "halted"
        elif protocol is None:
            status = "unsupported"
        elif observation is None:
            status = "calibrating"
        elif now_ms - observation.timestamp_ms > STALE_MS:
            status = "stale"
        elif observation.confidence < MIN_CONFIDENCE or not observation.metric_is_visible(protocol.metric):
            status = "lost_visibility"
        elif observation.view != protocol.required_view:
            status = "wrong_view"
        elif protocol.metric not in observation.metrics:
            status = "lost_visibility"
        elif not self._calibrated:
            status = "calibrating"
        else:
            status = "tracking"
        hold_seconds = 0
        if protocol and protocol.hold and self._hold_started is not None and status == "tracking":
            hold_seconds = max(0, (now_ms - self._hold_started) // 1_000)
        return {
            "status": status,
            "protocol_id": protocol.id if protocol else None,
            "tracking_supported": protocol is not None,
            "required_view": protocol.required_view if protocol else None,
            "calibration_required": protocol is not None,
            "calibrated": self._calibrated,
            "reps": self.reps,
            "hold_seconds": hold_seconds,
            "issues": list(self._issues),
            "cue": self._cue,
            "halted": self.halted,
            "observed_at_ms": observation.timestamp_ms if observation else None,
        }
