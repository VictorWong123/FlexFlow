"""Opt-in, bounded-cost smoke checks for FlexFlow's live backend.

Normal test collection only imports this module. External I/O starts only after both
``--confirm-live`` and ``FLEXFLOW_RUN_LIVE_SMOKE=1`` are present.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse
import uuid
import wave

import httpx
from dotenv import load_dotenv
from livekit import api, rtc
import psutil


load_dotenv(".env.local")
load_dotenv()


AGENT_NAME = "flexflow-coach"
LIVE_GUARD_ENV = "FLEXFLOW_RUN_LIVE_SMOKE"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 5.0
RTC_CONNECT_TIMEOUT_SECONDS = 15.0
MEDIA_STAGE_TIMEOUT_SECONDS = 30.0
SAFETY_STAGE_TIMEOUT_SECONDS = 20.0
VIDEO_WIDTH = 320
VIDEO_HEIGHT = 240
VIDEO_FPS = 5
LOCAL_CLEANUP_TIMEOUT_SECONDS = 10.0
WORKER_MARKER_ENV = "FLEXFLOW_SMOKE_WORKER_ID"


class SmokeError(RuntimeError):
    """Expected smoke failure safe to print without a traceback."""


@dataclass
class CallBudget:
    """Fail closed before any provider action exceeds its profile budget."""

    limits: dict[str, int]
    counts: dict[str, int] = field(default_factory=dict)

    def claim(self, action: str) -> None:
        next_count = self.counts.get(action, 0) + 1
        if next_count > self.limits.get(action, 0):
            raise SmokeError(f"call budget exceeded: {action}")
        self.counts[action] = next_count

    def report(self) -> dict[str, int]:
        return {name: self.counts.get(name, 0) for name in sorted(self.limits)}


def require_live_confirmation(*, confirm_live: bool, environ: dict[str, str] | os._Environ[str] = os.environ) -> None:
    """Guard every live profile before sockets, subprocesses, or temp media."""
    if not confirm_live or environ.get(LIVE_GUARD_ENV) != "1":
        raise SmokeError(
            f"live smoke disabled; pass --confirm-live and set {LIVE_GUARD_ENV}=1"
        )


def _required_livekit_env(environ: dict[str, str] | os._Environ[str]) -> tuple[str, str, str]:
    values = tuple(environ.get(name, "") for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))
    if not all(values):
        raise SmokeError("missing LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET")
    url, key, secret = values
    parsed = urlparse(url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise SmokeError("LIVEKIT_URL must use ws:// or wss://")
    return url, key, secret


async def _probe(http_get: Callable[..., Awaitable[Any]], base_url: str, path: str) -> float:
    started = time.monotonic()
    response = await http_get(f"{base_url.rstrip('/')}{path}", timeout=HTTP_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise SmokeError(f"{path} returned HTTP {response.status_code}")
    try:
        body = response.json()
    except (TypeError, ValueError) as exc:
        raise SmokeError(f"{path} returned invalid JSON") from exc
    if body.get("status") != "ok" or body.get("service") != "flexflow":
        raise SmokeError(f"{path} did not return FlexFlow status ok")
    return round((time.monotonic() - started) * 1000, 1)


async def run_status(
    *,
    backend_url: str,
    environ: dict[str, str] | os._Environ[str] = os.environ,
    http_get: Callable[..., Awaitable[Any]] | None = None,
    livekit_factory: Callable[..., Any] = api.LiveKitAPI,
) -> dict[str, Any]:
    """Probe health/readiness and spend exactly one LiveKit control-plane call."""
    require_live_confirmation(confirm_live=True, environ=environ)
    if http_get is None:
        raise ValueError("run_status requires an owned async HTTP client")
    budget = CallBudget({"gemini_sessions": 0, "livekit_list_rooms": 1})
    health_ms = await _probe(http_get, backend_url, "/health")
    ready_ms = await _probe(http_get, backend_url, "/ready")
    url, key, secret = _required_livekit_env(environ)
    started = time.monotonic()
    client = livekit_factory(url=url, api_key=key, api_secret=secret)
    try:
        budget.claim("livekit_list_rooms")
        await client.room.list_rooms(api.ListRoomsRequest())
    finally:
        await client.aclose()
    return {
        "backend_health": "ok",
        "backend_ready": "ok",
        "livekit_control_plane": "ok",
        "overall_status": "ok",
        "calls": budget.report(),
        "timings_ms": {
            "health": health_ms,
            "ready": ready_ms,
            "livekit": round((time.monotonic() - started) * 1000, 1),
        },
    }


def _validate_stop_wav(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with wave.open(str(path), "rb") as wav:
            return (
                wav.getframerate() == 16_000
                and wav.getsampwidth() == 2
                and wav.getnchannels() == 1
                and wav.getnframes() > 0
            )
    except (EOFError, OSError, wave.Error):
        return False


def _make_stop_wav(
    path: Path,
    *,
    platform_name: str = os.name,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$outputPath = [Environment]::GetEnvironmentVariable('FLEXFLOW_SMOKE_WAV_PATH'); "
        "if ([string]::IsNullOrWhiteSpace($outputPath)) { throw 'Missing output path' }; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        "try { $s.SetOutputToWaveFile($outputPath, $f); $s.Speak('stop') } "
        "finally { $s.Dispose() }"
    )
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    child_env = os.environ.copy()
    child_env["FLEXFLOW_SMOKE_WAV_PATH"] = str(path.resolve())
    if platform_name == "nt":
        try:
            sapi_result = runner(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_script,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                env=child_env,
            )
            if sapi_result.returncode == 0 and _validate_stop_wav(path):
                return "sapi"
        except (OSError, subprocess.SubprocessError):
            pass

    with suppress(OSError):
        path.unlink()
    try:
        flite_result = runner(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "flite=text=stop",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SmokeError("local offline speech preflight failed") from exc
    if flite_result.returncode != 0 or not _validate_stop_wav(path):
        raise SmokeError("local offline speech preflight failed")
    return "ffmpeg_flite"


@dataclass(frozen=True)
class WorkerHandle:
    process: subprocess.Popen[bytes]
    marker: str
    created_at: float


def _start_worker() -> WorkerHandle:
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    marker = str(uuid.uuid4())
    worker_env = os.environ.copy()
    worker_env[WORKER_MARKER_ENV] = marker
    process = subprocess.Popen(
        [sys.executable, "-m", "app.agent", "start"],
        cwd=Path(__file__).parents[2],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        env=worker_env,
        start_new_session=os.name != "nt",
    )
    try:
        created_at = psutil.Process(process.pid).create_time()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        created_at = 0.0
    return WorkerHandle(process=process, marker=marker, created_at=created_at)


def _tagged_worker_processes(marker: str) -> list[psutil.Process]:
    matches: list[psutil.Process] = []
    for process in psutil.process_iter(["pid"]):
        try:
            if process.environ().get(WORKER_MARKER_ENV) == marker:
                matches.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            continue
    return matches


def _known_worker_processes(handle: WorkerHandle) -> list[psutil.Process]:
    processes = {process.pid: process for process in _tagged_worker_processes(handle.marker)}
    try:
        parent = psutil.Process(handle.process.pid)
        if handle.created_at and abs(parent.create_time() - handle.created_at) < 0.01:
            processes[parent.pid] = parent
            for child in parent.children(recursive=True):
                processes[child.pid] = child
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
    return list(processes.values())


async def _stop_worker_tree(worker: WorkerHandle | subprocess.Popen[bytes]) -> None:
    """Stop tagged descendants even when the original launcher already exited."""
    if isinstance(worker, WorkerHandle):
        handle = worker
    else:
        try:
            created_at = psutil.Process(worker.pid).create_time()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return
        handle = WorkerHandle(process=worker, marker="", created_at=created_at)
    deadline = time.monotonic() + LOCAL_CLEANUP_TIMEOUT_SECONDS
    empty_scans = 0
    while time.monotonic() < deadline:
        processes = _known_worker_processes(handle)
        if not processes:
            empty_scans += 1
            if empty_scans >= 2:
                return
            await asyncio.sleep(0.1)
            continue
        empty_scans = 0
        original = next(
            (
                process
                for process in processes
                if process.pid == handle.process.pid
            ),
            None,
        )
        if original is not None and os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(original.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        elif original is not None:  # pragma: no cover - Unix CI only.
            with suppress(ProcessLookupError):
                os.killpg(original.pid, signal.SIGTERM)
        for process in sorted(processes, key=lambda item: item.pid, reverse=True):
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                process.terminate()
        _, alive = await asyncio.to_thread(psutil.wait_procs, processes, timeout=1.0)
        for process in alive:
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                process.kill()
        if alive:
            await asyncio.to_thread(psutil.wait_procs, alive, timeout=1.0)

        await asyncio.sleep(0.05)
    if _known_worker_processes(handle):
        raise SmokeError("worker cleanup failed")


@contextmanager
def _temporary_media_file(**kwargs: Any):
    base = Path(kwargs.pop("dir", os.getenv("TEMP", Path.cwd())))
    prefix = str(kwargs.pop("prefix", "flexflow-smoke-"))
    if kwargs:
        raise TypeError(f"unsupported temporary media options: {sorted(kwargs)}")
    path = base / f"{prefix}{uuid.uuid4()}.wav"
    try:
        yield str(path)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise SmokeError("temporary media cleanup failed") from exc
        if path.exists():
            raise SmokeError("temporary media cleanup failed")


async def _cleanup_headless(
    *,
    room: Any | None,
    connected: bool,
    worker: Any | None,
    video_task: asyncio.Task[None] | None,
    video_stop: asyncio.Event,
    stop_worker: Callable[[Any], Awaitable[None]],
) -> None:
    """Release local RTC/process resources; separate seam keeps failure cleanup testable."""
    failures: list[BaseException] = []
    video_stop.set()
    if video_task is not None:
        try:
            await asyncio.wait_for(video_task, LOCAL_CLEANUP_TIMEOUT_SECONDS)
        except (asyncio.CancelledError, Exception) as exc:
            failures.append(exc)
    if room is not None and connected:
        try:
            await asyncio.wait_for(room.disconnect(), LOCAL_CLEANUP_TIMEOUT_SECONDS)
        except Exception as exc:
            failures.append(exc)
    if worker is not None:
        try:
            await asyncio.wait_for(
                stop_worker(worker), LOCAL_CLEANUP_TIMEOUT_SECONDS + 2
            )
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise SmokeError("local cleanup failed") from failures[0]


def _participant_token(url: str, key: str, secret: str, room_name: str) -> str:
    del url
    return (
        api.AccessToken(key, secret)
        .with_identity(f"smoke-{uuid.uuid4()}")
        .with_name("FlexFlow headless smoke")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]
            )
        )
        .to_jwt()
    )


async def _publish_blank_video(room: rtc.Room, stop: asyncio.Event) -> None:
    source = rtc.VideoSource(VIDEO_WIDTH, VIDEO_HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("synthetic-blank", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_CAMERA
    publication = await room.local_participant.publish_track(track, options)
    frame = rtc.VideoFrame(
        VIDEO_WIDTH,
        VIDEO_HEIGHT,
        rtc.VideoBufferType.RGB24,
        bytes(VIDEO_WIDTH * VIDEO_HEIGHT * 3),
    )
    try:
        while not stop.is_set():
            source.capture_frame(frame)
            await asyncio.sleep(1 / VIDEO_FPS)
    finally:
        await room.local_participant.unpublish_track(publication.sid)


async def _publish_wav(room: rtc.Room, path: Path) -> None:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() not in {1, 2}:
            raise SmokeError("SAPI produced unsupported PCM format")
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        samples_per_chunk = max(1, sample_rate // 50)
        source = rtc.AudioSource(sample_rate, channels)
        track = rtc.LocalAudioTrack.create_audio_track("synthetic-stop", source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_MICROPHONE
        publication = await room.local_participant.publish_track(track, options)
        try:
            while data := wav.readframes(samples_per_chunk):
                samples = len(data) // (2 * channels)
                await source.capture_frame(rtc.AudioFrame(data, sample_rate, channels, samples))
            await source.wait_for_playout()
        finally:
            await room.local_participant.unpublish_track(publication.sid)


async def _wait(event: asyncio.Event, seconds: float, stage: str) -> None:
    try:
        await asyncio.wait_for(event.wait(), seconds)
    except TimeoutError as exc:
        raise SmokeError(f"timeout waiting for {stage}") from exc


async def run_headless(
    *,
    environ: dict[str, str] | os._Environ[str] = os.environ,
    sapi: Callable[[Path], None] = _make_stop_wav,
    worker_factory: Callable[[], WorkerHandle] = _start_worker,
    room_factory: Callable[[], rtc.Room] = rtc.Room,
    livekit_factory: Callable[..., Any] = api.LiveKitAPI,
    stop_worker: Callable[[Any], Awaitable[None]] = _stop_worker_tree,
    temporary_media: Callable[..., AbstractContextManager[str]] = _temporary_media_file,
) -> dict[str, Any]:
    """Run one no-playback RTC/Gemini session with deterministic cleanup."""
    require_live_confirmation(confirm_live=True, environ=environ)
    url, key, secret = _required_livekit_env(environ)
    budget = CallBudget({"gemini_sessions": 1, "livekit_delete_room": 1, "livekit_list_rooms": 0})
    room_name = str(uuid.uuid4())
    room: rtc.Room | None = None
    worker: Any | None = None
    video_task: asyncio.Task[None] | None = None
    video_stop = asyncio.Event()
    api_client: Any | None = None
    connected = False
    cloud_attempted = False
    result: dict[str, Any] | None = None

    temp_path: str | None = None
    try:
        with temporary_media(prefix="flexflow-smoke-") as temp_path:
            wav_path = Path(temp_path)
            sapi(wav_path)  # Must succeed before any provider connection or worker start.
            try:
                worker = worker_factory()
                room = room_factory()
                agent_joined = asyncio.Event()
                greeting_audio = asyncio.Event()
                tracking_received = asyncio.Event()
                halted = asyncio.Event()
                resumed = asyncio.Event()
                saw_halt = False

                def on_participant_connected(_participant: Any) -> None:
                    agent_joined.set()

                def on_track_subscribed(
                    track: Any, _publication: Any, _participant: Any
                ) -> None:
                    if track.kind != rtc.TrackKind.KIND_AUDIO:
                        return

                    async def consume_one_frame() -> None:
                        stream = rtc.AudioStream(track)
                        try:
                            async for _event in stream:
                                greeting_audio.set()
                                break
                        finally:
                            await stream.aclose()

                    asyncio.create_task(consume_one_frame())

                def on_data_received(packet: Any) -> None:
                    nonlocal saw_halt
                    if getattr(packet, "topic", "") != "tracking":
                        return
                    try:
                        data = json.loads(bytes(packet.data).decode("utf-8"))
                    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
                        return
                    if not isinstance(data, dict) or data.get("status") not in {
                        "unsupported", "calibrating", "stale", "lost_visibility",
                        "wrong_view", "tracking", "halted",
                    }:
                        return
                    tracking_received.set()
                    if data.get("halted") is True and data.get("status") == "halted":
                        saw_halt = True
                        halted.set()
                    elif saw_halt and data.get("halted") is False:
                        resumed.set()

                room.on("participant_connected", on_participant_connected)
                room.on("track_subscribed", on_track_subscribed)
                room.on("data_received", on_data_received)

                budget.claim("gemini_sessions")
                cloud_attempted = True
                await asyncio.wait_for(
                    room.connect(url, _participant_token(url, key, secret, room_name)),
                    RTC_CONNECT_TIMEOUT_SECONDS,
                )
                connected = True
                video_task = asyncio.create_task(_publish_blank_video(room, video_stop))
                await _wait(agent_joined, MEDIA_STAGE_TIMEOUT_SECONDS, "agent participant")
                await _wait(greeting_audio, MEDIA_STAGE_TIMEOUT_SECONDS, "greeting audio")
                await _wait(tracking_received, MEDIA_STAGE_TIMEOUT_SECONDS, "tracking packet")
                await asyncio.wait_for(
                    _publish_wav(room, wav_path), SAFETY_STAGE_TIMEOUT_SECONDS
                )
                await _wait(halted, SAFETY_STAGE_TIMEOUT_SECONDS, "safety halt")
                await room.local_participant.publish_data(
                    json.dumps({"type": "RESUME_AFTER_SAFETY"}).encode(),
                    reliable=True,
                    topic="control",
                )
                await _wait(resumed, SAFETY_STAGE_TIMEOUT_SECONDS, "safety resume")
                result = {
                    "agent_dispatch": "ok",
                    "gemini_audio": "ok",
                    "tracking": "ok",
                    "safety_halt": "ok",
                    "safety_resume": "ok",
                    "overall_status": "ok",
                }
            finally:
                try:
                    await _cleanup_headless(
                        room=room,
                        connected=connected,
                        worker=worker,
                        video_task=video_task,
                        video_stop=video_stop,
                        stop_worker=stop_worker,
                    )
                finally:
                    if cloud_attempted:
                        api_client = livekit_factory(url=url, api_key=key, api_secret=secret)
                        try:
                            budget.claim("livekit_delete_room")
                            try:
                                await api_client.room.delete_room(api.DeleteRoomRequest(room=room_name))
                            except Exception as exc:
                                if result is not None:
                                    raise SmokeError("room cleanup failed") from exc
                        finally:
                            await api_client.aclose()
    except OSError as exc:
        if temp_path is not None and Path(temp_path).exists():
            raise SmokeError("temporary media cleanup failed") from exc
        raise
    if temp_path is not None and Path(temp_path).exists():
        raise SmokeError("temporary media cleanup failed")
    if result is None:  # pragma: no cover - successful path always assigns result.
        raise SmokeError("headless smoke ended without a result")
    result["calls"] = budget.report()
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Opt-in FlexFlow backend smoke checks")
    subparsers = parser.add_subparsers(dest="profile", required=True)
    status = subparsers.add_parser("status", help="health/readiness plus one LiveKit list request")
    status.add_argument("--confirm-live", action="store_true")
    status.add_argument("--backend-url", default=os.getenv("FLEXFLOW_BACKEND_URL", DEFAULT_BACKEND_URL))
    headless = subparsers.add_parser("headless", help="one headless RTC/Gemini session")
    headless.add_argument("--confirm-live", action="store_true")
    return parser


async def _main(args: argparse.Namespace) -> dict[str, Any]:
    require_live_confirmation(confirm_live=args.confirm_live)
    if args.profile == "status":
        async with httpx.AsyncClient() as client:
            return await run_status(backend_url=args.backend_url, http_get=client.get)
    return await run_headless()


def main() -> int:
    args = _parser().parse_args()
    try:
        result = asyncio.run(_main(args))
    except Exception as exc:
        error = str(exc) if isinstance(exc, SmokeError) else type(exc).__name__
        print(json.dumps({"overall_status": "failed", "error": error}, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
