from __future__ import annotations

import asyncio
import base64
from contextlib import nullcontext, suppress
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
import uuid
import wave

import pytest
import jwt
from pytest_socket import SocketConnectBlockedError

from app.scripts import smoke_backend


def test_default_test_policy_blocks_sockets() -> None:
    with pytest.warns(UserWarning, match="192.0.2.1"):
        with pytest.raises(SocketConnectBlockedError):
            socket.create_connection(("192.0.2.1", 443), timeout=0.01)


class FakeResponse:
    status_code = 200

    def json(self) -> dict[str, str]:
        return {"status": "ok", "service": "flexflow"}


def absent_temp_media(**_kwargs: object):
    return nullcontext(str(Path.cwd() / f".absent-smoke-{uuid.uuid4()}.wav"))


class FakeLiveKit:
    def __init__(self) -> None:
        self.list_calls = 0
        self.closed = False
        self.room = self

    async def list_rooms(self, _request: object) -> object:
        self.list_calls += 1
        return object()

    async def aclose(self) -> None:
        self.closed = True


def test_live_confirmation_requires_flag_and_environment() -> None:
    with pytest.raises(smoke_backend.SmokeError):
        smoke_backend.require_live_confirmation(confirm_live=False, environ={})
    with pytest.raises(smoke_backend.SmokeError):
        smoke_backend.require_live_confirmation(confirm_live=True, environ={})
    smoke_backend.require_live_confirmation(
        confirm_live=True, environ={smoke_backend.LIVE_GUARD_ENV: "1"}
    )


def test_budget_fails_before_extra_provider_call() -> None:
    budget = smoke_backend.CallBudget({"livekit_list_rooms": 1, "gemini_sessions": 0})
    budget.claim("livekit_list_rooms")
    with pytest.raises(smoke_backend.SmokeError):
        budget.claim("livekit_list_rooms")
    with pytest.raises(smoke_backend.SmokeError):
        budget.claim("gemini_sessions")
    assert budget.report() == {"gemini_sessions": 0, "livekit_list_rooms": 1}


def test_participant_token_is_local_room_scoped_and_names_agent_dispatch() -> None:
    token = smoke_backend._participant_token(
        "wss://livekit.example", "key", "s" * 32, "room-id"
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["video"]["room"] == "room-id"
    assert claims["video"]["roomJoin"] is True
    assert claims["roomConfig"]["agents"] == [{"agentName": "flexflow-coach"}]


def test_sapi_uses_encoded_command_and_produces_valid_bounded_wav() -> None:
    path = Path.cwd() / f".sapi contract {uuid.uuid4()}.wav"
    invocation: dict[str, object] = {}

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        invocation["argv"] = argv
        invocation["env"] = kwargs["env"]
        output_path = Path(kwargs["env"]["FLEXFLOW_SMOKE_WAV_PATH"])  # type: ignore[index]
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
            wav.writeframes(bytes(320))
        return subprocess.CompletedProcess(argv, 0, "", "")

    try:
        assert smoke_backend._make_stop_wav(
            path, platform_name="nt", runner=runner
        ) == "sapi"

        argv = invocation["argv"]
        assert isinstance(argv, list)
        assert argv[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
        decoded = base64.b64decode(argv[4]).decode("utf-16-le")
        assert "FLEXFLOW_SMOKE_WAV_PATH" in decoded
        assert str(path) not in " ".join(argv)
        assert invocation["env"]["FLEXFLOW_SMOKE_WAV_PATH"] == str(path.resolve())  # type: ignore[index]
        with wave.open(str(path), "rb") as wav:
            assert (wav.getframerate(), wav.getsampwidth(), wav.getnchannels()) == (16_000, 2, 1)
    finally:
        path.unlink(missing_ok=True)


def test_sapi_failure_falls_back_to_offline_ffmpeg_flite() -> None:
    path = Path.cwd() / f".flite contract {uuid.uuid4()}.wav"
    invocations: list[tuple[list[str], dict[str, object]]] = []

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        invocations.append((argv, kwargs))
        if argv[0] == "powershell.exe":
            return subprocess.CompletedProcess(argv, 1, "", "voice unavailable")
        assert argv[0] == "ffmpeg"
        assert "flite=text=stop" in argv
        assert argv[argv.index("-ar") + 1] == "16000"
        assert argv[argv.index("-ac") + 1] == "1"
        assert argv[argv.index("-c:a") + 1] == "pcm_s16le"
        with wave.open(argv[-1], "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
            wav.writeframes(bytes(320))
        return subprocess.CompletedProcess(argv, 0, "", "")

    try:
        assert smoke_backend._make_stop_wav(
            path, platform_name="nt", runner=runner
        ) == "ffmpeg_flite"
        assert [argv[0] for argv, _kwargs in invocations] == ["powershell.exe", "ffmpeg"]
        assert all(kwargs["capture_output"] is True for _argv, kwargs in invocations)
        assert all(kwargs["text"] is True for _argv, kwargs in invocations)
        assert smoke_backend._validate_stop_wav(path)
    finally:
        path.unlink(missing_ok=True)


def test_offline_speech_preflight_fails_closed_when_both_engines_fail() -> None:
    path = Path.cwd() / f".tts failure {uuid.uuid4()}.wav"
    engines: list[str] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        engines.append(argv[0])
        return subprocess.CompletedProcess(argv, 1, "", "hidden diagnostic")

    try:
        with pytest.raises(smoke_backend.SmokeError, match="local offline speech preflight failed"):
            smoke_backend._make_stop_wav(path, platform_name="nt", runner=runner)
        assert engines == ["powershell.exe", "ffmpeg"]
        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_temporary_media_file_is_removed() -> None:
    path: Path | None = None
    with smoke_backend._temporary_media_file(
        prefix=".smoke-cleanup-", dir=Path.cwd()
    ) as temp_path:
        path = Path(temp_path)
        path.write_bytes(b"temporary")
        assert path.is_file()
    assert path is not None
    assert not path.exists()


def test_status_uses_one_livekit_call_and_zero_gemini() -> None:
    async def check() -> None:
        paths: list[str] = []
        client = FakeLiveKit()

        async def get(url: str, **_kwargs: object) -> FakeResponse:
            paths.append(url)
            return FakeResponse()

        result = await smoke_backend.run_status(
            backend_url="http://backend",
            environ={
                smoke_backend.LIVE_GUARD_ENV: "1",
                "LIVEKIT_URL": "wss://livekit.example",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "secret",
            },
            http_get=get,
            livekit_factory=lambda **_kwargs: client,
        )
        assert paths == ["http://backend/health", "http://backend/ready"]
        assert client.list_calls == 1
        assert client.closed
        assert result["calls"] == {"gemini_sessions": 0, "livekit_list_rooms": 1}

    asyncio.run(check())


def test_cleanup_releases_video_room_and_worker_after_failure() -> None:
    async def check() -> None:
        stopped = asyncio.Event()
        video_stop = asyncio.Event()
        room = SimpleNamespace(disconnect=None)
        room.disconnected = False

        async def disconnect() -> None:
            room.disconnected = True

        async def video() -> None:
            await video_stop.wait()
            raise RuntimeError("synthetic failure")

        async def stop_worker(worker: object) -> None:
            assert worker == "worker"
            stopped.set()

        room.disconnect = disconnect
        task = asyncio.create_task(video())
        with pytest.raises(smoke_backend.SmokeError, match="local cleanup failed"):
            await smoke_backend._cleanup_headless(
                room=room,
                connected=True,
                worker="worker",
                video_task=task,
                video_stop=video_stop,
                stop_worker=stop_worker,
            )
        assert room.disconnected
        assert stopped.is_set()
        assert task.done()

    asyncio.run(check())


def test_disconnect_failure_still_stops_worker_and_fails_cleanup() -> None:
    async def check() -> None:
        stopped = asyncio.Event()
        video_stop = asyncio.Event()

        class Room:
            async def disconnect(self) -> None:
                raise RuntimeError("private disconnect diagnostic")

        async def video() -> None:
            await video_stop.wait()

        async def stop_worker(_worker: object) -> None:
            stopped.set()

        task = asyncio.create_task(video())
        with pytest.raises(smoke_backend.SmokeError, match="^local cleanup failed$"):
            await smoke_backend._cleanup_headless(
                room=Room(),
                connected=True,
                worker=object(),
                video_task=task,
                video_stop=video_stop,
                stop_worker=stop_worker,
            )
        assert task.done()
        assert stopped.is_set()

    asyncio.run(check())


def test_headless_sapi_failure_happens_before_cloud_or_worker() -> None:
    calls: list[str] = []

    def fail_sapi(_path: object) -> None:
        calls.append("sapi")
        raise smoke_backend.SmokeError("preflight")

    with pytest.raises(smoke_backend.SmokeError, match="preflight"):
        asyncio.run(smoke_backend.run_headless(
            environ={
                smoke_backend.LIVE_GUARD_ENV: "1",
                "LIVEKIT_URL": "wss://livekit.example",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "secret",
            },
            sapi=fail_sapi,
            worker_factory=lambda: calls.append("worker"),  # type: ignore[arg-type,return-value]
            room_factory=lambda: calls.append("room"),  # type: ignore[arg-type,return-value]
            livekit_factory=lambda **_kwargs: calls.append("api"),
            temporary_media=absent_temp_media,
        ))
    assert calls == ["sapi"]


def test_headless_success_claims_budget_halts_resumes_and_cleans(monkeypatch) -> None:
    async def check() -> None:
        events: list[str] = []
        handlers: dict[str, object] = {}

        class AudioStream:
            def __init__(self, _track: object) -> None:
                pass

            def __aiter__(self):
                async def frames():
                    yield object()
                return frames()

            async def aclose(self) -> None:
                events.append("audio_closed")

        class LocalParticipant:
            async def publish_data(self, _payload: bytes, **_kwargs: object) -> None:
                events.append("resume_control")
                handlers["data_received"](SimpleNamespace(
                    topic="tracking",
                    data=b'{"status":"calibrating","halted":false}',
                ))

        class Room:
            local_participant = LocalParticipant()

            def on(self, event: str, callback: object) -> None:
                handlers[event] = callback

            async def connect(self, _url: str, _token: str) -> None:
                events.append("connect")
                handlers["participant_connected"](object())
                handlers["track_subscribed"](
                    SimpleNamespace(kind=smoke_backend.rtc.TrackKind.KIND_AUDIO),
                    object(),
                    object(),
                )
                handlers["data_received"](SimpleNamespace(
                    topic="tracking",
                    data=b'{"status":"calibrating","halted":false}',
                ))

            async def disconnect(self) -> None:
                events.append("disconnect")

        class ApiClient:
            room = None

            def __init__(self) -> None:
                self.room = self

            async def delete_room(self, _request: object) -> None:
                events.append("delete_room")

            async def aclose(self) -> None:
                events.append("api_closed")

        async def video(_room: object, stopped: asyncio.Event) -> None:
            events.append("video")
            await stopped.wait()

        async def audio(_room: object, _path: Path) -> None:
            events.append("stop_audio")
            handlers["data_received"](SimpleNamespace(
                topic="tracking",
                data=b'{"status":"halted","halted":true}',
            ))

        async def stop_worker(_worker: object) -> None:
            events.append("worker_stopped")

        original_claim = smoke_backend.CallBudget.claim

        def claim(budget: smoke_backend.CallBudget, action: str) -> None:
            events.append(f"claim:{action}")
            original_claim(budget, action)

        monkeypatch.setattr(smoke_backend.CallBudget, "claim", claim)
        monkeypatch.setattr(smoke_backend, "_publish_blank_video", video)
        monkeypatch.setattr(smoke_backend, "_publish_wav", audio)
        monkeypatch.setattr(smoke_backend.rtc, "AudioStream", AudioStream)

        result = await smoke_backend.run_headless(
            environ={
                smoke_backend.LIVE_GUARD_ENV: "1",
                "LIVEKIT_URL": "wss://livekit.example",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "s" * 32,
            },
            sapi=lambda _path: events.append("sapi"),
            worker_factory=lambda: object(),  # type: ignore[arg-type]
            room_factory=Room,
            livekit_factory=lambda **_kwargs: ApiClient(),
            stop_worker=stop_worker,
            temporary_media=absent_temp_media,
        )

        assert result["overall_status"] == "ok"
        assert result["safety_halt"] == result["safety_resume"] == "ok"
        assert result["calls"] == {
            "gemini_sessions": 1,
            "livekit_delete_room": 1,
            "livekit_list_rooms": 0,
        }
        assert events.index("claim:gemini_sessions") < events.index("connect")
        assert events.index("claim:livekit_delete_room") < events.index("delete_room")
        assert "disconnect" in events
        assert "worker_stopped" in events
        assert "api_closed" in events

    asyncio.run(check())


def test_headless_connect_failure_still_deletes_room_and_stops_worker() -> None:
    async def check() -> None:
        events: list[str] = []

        class Room:
            local_participant = SimpleNamespace()

            def on(self, _event: str, _callback: object) -> None:
                pass

            async def connect(self, _url: str, _token: str) -> None:
                events.append("connect")
                raise RuntimeError("offline connect failure")

        class ApiClient:
            room = None

            def __init__(self) -> None:
                self.room = self

            async def delete_room(self, _request: object) -> None:
                events.append("delete_room")

            async def aclose(self) -> None:
                events.append("api_closed")

        async def stop_worker(_worker: object) -> None:
            events.append("worker_stopped")

        with pytest.raises(RuntimeError, match="offline connect failure"):
            await smoke_backend.run_headless(
                environ={
                    smoke_backend.LIVE_GUARD_ENV: "1",
                    "LIVEKIT_URL": "wss://livekit.example",
                    "LIVEKIT_API_KEY": "key",
                    "LIVEKIT_API_SECRET": "s" * 32,
                },
                sapi=lambda _path: events.append("sapi"),
                worker_factory=lambda: object(),  # type: ignore[arg-type]
                room_factory=Room,
                livekit_factory=lambda **_kwargs: ApiClient(),
                stop_worker=stop_worker,
                temporary_media=absent_temp_media,
            )
        assert events == ["sapi", "connect", "worker_stopped", "delete_room", "api_closed"]

    asyncio.run(check())


def test_worker_cleanup_finds_child_after_launcher_exits() -> None:
    marker = str(uuid.uuid4())
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "time.sleep(0.2)"
    )
    worker_env = smoke_backend.os.environ.copy()
    worker_env[smoke_backend.WORKER_MARKER_ENV] = marker
    process = subprocess.Popen(
        [smoke_backend.sys.executable, "-c", parent_code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=worker_env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    handle = smoke_backend.WorkerHandle(
        process=process,  # type: ignore[arg-type]
        marker=marker,
        created_at=smoke_backend.psutil.Process(process.pid).create_time(),
    )
    try:
        process.wait(timeout=5)
        deadline = smoke_backend.time.monotonic() + 3
        while (
            not smoke_backend._tagged_worker_processes(marker)
            and smoke_backend.time.monotonic() < deadline
        ):
            smoke_backend.time.sleep(0.05)
        assert smoke_backend._tagged_worker_processes(marker)
        asyncio.run(smoke_backend._stop_worker_tree(handle))
        assert smoke_backend._tagged_worker_processes(marker) == []
    finally:
        for descendant in smoke_backend._tagged_worker_processes(marker):
            with suppress(smoke_backend.psutil.NoSuchProcess):
                descendant.kill()
