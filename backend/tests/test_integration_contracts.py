from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Response

import main
from app.services import exercise_db


def test_readiness_requires_runtime_configuration(monkeypatch) -> None:
    for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    response = Response()
    result = asyncio.run(main.ready(response))
    assert response.status_code == 503
    assert result.status == "not_ready"


def test_readiness_checks_livekit_url_and_pose_model(monkeypatch) -> None:
    for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GOOGLE_API_KEY"):
        monkeypatch.setenv(name, "configured")
    assert main._POSE_MODEL_PATH.is_file()

    monkeypatch.setenv("LIVEKIT_URL", "https://not-websocket.example")
    response = Response()
    assert asyncio.run(main.ready(response)).status == "not_ready"
    assert response.status_code == 503

    monkeypatch.setenv("LIVEKIT_URL", "wss://livekit.example")
    response = Response()
    assert asyncio.run(main.ready(response)).status == "ok"
    assert response.status_code == 200

    monkeypatch.setattr(main, "_POSE_MODEL_PATH", Path(__file__).parent / "missing.task")
    response = Response()
    assert asyncio.run(main.ready(response)).status == "not_ready"


def test_start_script_cleans_up_health_process() -> None:
    script = (Path(__file__).parents[1] / "start.sh").read_text(encoding="utf-8")
    assert "trap cleanup EXIT INT TERM" in script
    assert 'kill "$health_pid"' in script
    assert 'kill "$agent_pid"' in script
    assert 'wait -n "$health_pid" "$agent_pid"' in script


def test_migration_grants_and_owner_policies() -> None:
    migration = next((Path(__file__).parents[2] / "frontend/supabase/migrations").glob("*.sql")).read_text(encoding="utf-8")
    assert "revoke insert, update, delete on table public.session_summaries" in migration.lower()
    assert 'create policy "session_summaries_owner_insert"' not in migration.lower()
    assert 'create policy "session_summaries_owner_update"' not in migration.lower()
    assert 'create policy "session_summaries_owner_delete"' not in migration.lower()
    assert "unique index" in migration.lower()
    assert "with check ((select auth.uid()) = user_id)" in migration.lower()
    assert migration.lower().count("(select auth.uid()) = user_id") >= 5
    assert migration.lower().count("security definer set search_path = ''") == 6
    assert migration.lower().count("caller_id is null") == 6
    assert "revoke insert, update, delete on table public.therapy_sessions" in migration.lower()
    assert migration.lower().count("grant execute on function public.") >= 5
    assert "session_quota_exceeded" in migration
    assert "delete_session_summary" in migration
    assert "p_duration_seconds > 28800" in migration
    assert "jsonb_array_length(p_youtube_links) > 3" in migration


def test_exercise_catalog_uses_immutable_revision() -> None:
    revision = "b0eed061e1c832b3ed815fbaa4b45b3cdc14df49"
    assert revision in exercise_db._EXERCISES_URL
    assert revision in exercise_db._IMAGE_BASE
