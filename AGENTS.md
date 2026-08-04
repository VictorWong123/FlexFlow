# FlexFlow Repository Guide

## What This Repository Does

FlexFlow is a real-time movement coach. LiveKit carries audio, video, and data; MediaPipe extracts pose landmarks; deterministic `SessionCoach` protocols own rep, hold, form, confidence, and safety state; Gemini provides conversational voice coaching from those facts.

## Project Layout

- `backend/main.py`: FastAPI health and readiness service.
- `backend/app/agent.py`: LiveKit worker, Gemini Native Audio, tools, and session lifecycle.
- `backend/app/vision.py`: MediaPipe frame processing and throttled LiveKit tracking data.
- `backend/app/coach.py`: Deterministic exercise protocols and state machine.
- `backend/app/state.py`: Async per-session state shared by vision and Gemini tools.
- `backend/app/pain_guardrail.py`: Immediate stop/pain detection and fixed safety response.
- `frontend/app/api/`: Authenticated LiveKit token issuance and session-summary persistence.
- `frontend/components/VideoSession.tsx`: Live room, tracking UI, transcript, and session controls.
- `frontend/supabase/migrations/`: RLS, session registry, quotas, and lifecycle RPCs.

## Architecture Invariants

- MediaPipe and `SessionCoach` are authoritative for reps, holds, form issues, tracking confidence, and camera view. Do not ask Gemini to infer or remember these from video.
- Gemini receives audio and bounded structured state through tools. Keep raw video input disabled.
- Never store raw audio, video, landmarks, or full transcripts. Only validated bounded summaries may be persisted.
- Pain or stop signals must interrupt coaching, halt deterministic tracking, and require explicit user confirmation before resume.
- Keep the vision loop non-blocking: MediaPipe runs in its executor, stale frames are dropped, and ordinary tracking/landmark publications stay capped near 10 Hz. Only urgent safety or semantic transitions may bypass throttling.
- Treat LiveKit data packets, transcripts, model output, and API bodies as untrusted input. Validate and bound them at their boundary.
- Session rows are server-issued and user-owned. Preserve quotas, atomic claim/complete/release RPCs, RLS, and authenticated ownership checks.

## Backend Work

- Use Python 3.10+ and existing modules before adding dependencies or abstractions.
- Keep per-session mutable state in `AsyncState`; do not introduce process-global exercise state.
- Add or tune movement protocols in `backend/app/coach.py`. Document required camera view and validate thresholds with tests.
- Do not edit `backend/app/models/pose_landmarker_lite.task` manually.
- Environment variables belong in `backend/.env.local`; update `.env.example` with placeholders only.

Run backend checks from `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider
```

## Frontend and Database Work

- Frontend uses Next.js 15, React 19, TypeScript, Tailwind CSS, LiveKit, and Supabase.
- Keep server secrets out of client components and `NEXT_PUBLIC_*` variables.
- Parse LiveKit tracking packets with `frontend/utils/tracking.ts`; do not cast participant data directly.
- Preserve responsive layouts, keyboard access, visible focus, and safety announcements.
- Change schema through a new migration; do not rewrite a migration already applied outside local development.
- Keep `frontend/utils/supabase/database.types.ts` aligned with schema changes.
- Environment variables belong in `frontend/.env.local`; never commit credentials.

Run frontend checks from `frontend/`:

```bash
npm ci
npm run test
npm run typecheck
npm run lint
npm run build
npm audit --omit=dev
```

## Definition of Done

- Add the smallest regression test covering changed behavior.
- Run relevant backend and frontend checks from their documented working directories.
- Keep `git diff --check` clean.
- Update `README.md`, `.env.example`, and migration/types documentation when contracts change.
- Do not claim live-camera, LiveKit, Gemini, or Supabase verification without the required devices and credentials.
