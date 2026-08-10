# FlexFlow

Real-time AI movement coach: FastAPI health service + LiveKit Agents + Gemini Native Audio. MediaPipe Pose owns deterministic movement metrics; raw video/audio are not stored by FlexFlow.

## Requirements

- **Python 3.10+**
- LiveKit Cloud (or self-hosted) and **Google Gemini API key** (see below)

## Setup

**Backend** (requires Python 3.10+):

```bash
cd backend

# If you don't have Python 3.10+: brew install python@3.11

# One-time setup (creates venv + installs deps):
./setup.sh

# Or manually:
python3.11 -m venv .venv   # or python3.10, python3.12
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and edit env:
cp .env.example .env.local
# Add: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, GOOGLE_API_KEY
```

**Frontend:**
```bash
cd frontend
npm install
cp .env.example .env.local
# Add: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY,
# LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, GOOGLE_API_KEY
```

## Run

Use **3 terminals**:

**Terminal 1 – Backend HTTP:**
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 – LiveKit agent:**
```bash
cd backend
source .venv/bin/activate
python -m app.agent dev
```

**Terminal 3 – Frontend:**
```bash
cd frontend
npm run dev
```

Then open http://localhost:3000

## Layout

| Path | Role |
|------|------|
| `backend/main.py` | FastAPI app (health, ready) |
| `backend/app/agent.py` | FlexFlow agent entrypoint; Gemini realtime, `get_body_metrics`, pain guardrail |
| `backend/app/coach.py` | Deterministic `SessionCoach`, movement protocols, rep/hold/cue state |
| `backend/app/vision.py` | MediaPipe Pose observations and throttled tracking publication |
| `backend/app/state.py` | Per-session metrics and `SessionCoach` seam |
| `backend/app/utils/physics.py` | Reusable 3D joint-angle math |
| `backend/app/pain_guardrail.py` | Pain keywords and safety message |
| `frontend/app/api/token/route.ts` | Authenticated LiveKit token and session issuance |
| `frontend/app/api/save-session/route.ts` | Validated, idempotent summary lifecycle |
| `frontend/supabase/migrations/` | Session registry, summary schema, RLS, and lifecycle RPCs |

## Why do I need a Gemini API key? Doesn’t LiveKit run the LLM?

**LiveKit and Gemini do different jobs.**

- **LiveKit** (your `LIVEKIT_*` keys) runs the **real-time layer**: rooms, WebRTC, media (audio/video), and agent dispatch. It does **not** run or host Gemini. It doesn’t substitute for a Google API key.

- **Gemini** (your `GOOGLE_API_KEY`) runs the **model**: understanding, reasoning, and voice (the “AI” that follows instructions and uses `get_body_metrics`). Your FlexFlow worker calls **Google’s Gemini API** (e.g. Multimodal Live) from your backend; that call is authenticated with `GOOGLE_API_KEY`.

So: LiveKit = transport and orchestration; Gemini = the actual LLM/voice. You need both keys. LiveKit cannot “use Gemini for you” without you providing a Gemini API key, because the model always runs on Google’s side and is billed/authenticated via your Google Cloud / Gemini API key.

## Pain guardrail

Interim `stop` or `ouch` input is handled immediately; other pain words are checked on final transcripts. Word-boundary matches interrupt speech, halt tracking, and deliver a fixed warning. Resume requires explicit frontend confirmation.

## Frontend

The frontend is a Next.js app with React and Tailwind CSS. See `frontend/README.md` for setup.

```bash
cd frontend
npm install
npm run dev
```

## Test

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider

cd ../frontend
npm ci
npm run test
npm run typecheck
npm run lint
npm run build
```

Backend pytest blocks all outbound sockets, including when `.env.local` contains real
credentials. Provider smoke checks are manual-only and require two confirmations:
`--confirm-live` plus `FLEXFLOW_RUN_LIVE_SMOKE=1`.

### Low-cost live status check

Start backend HTTP service first, then run from `backend/`:

```powershell
$env:FLEXFLOW_RUN_LIVE_SMOKE = "1"
python -m app.scripts.smoke_backend status --confirm-live --backend-url http://127.0.0.1:8000
```

Expected compact JSON reports `/health`, `/ready`, and LiveKit control plane as `ok`.
Budget: exactly 2 backend HTTP requests, 1 LiveKit `list_rooms` request, 0 rooms, and
0 Gemini sessions. Command performs no retry.

### Full headless smoke

Run manually from `backend/`; backend worker must not already be running for this room:

```powershell
$env:FLEXFLOW_RUN_LIVE_SMOKE = "1"
python -m app.scripts.smoke_backend headless --confirm-live
```

Command first generates local offline audio saying `stop`, trying Windows SAPI and then the
`ffmpeg` `flite` filter when no usable SAPI voice exists. It never uses network TTS. Only
after local synthesis succeeds, it launches one worker, creates one UUID room through RTC named dispatch, publishes blank
in-memory RGB frames and ephemeral synthetic audio, and checks agent join, Gemini greeting
audio, tracking, safety halt, and explicit resume. Received audio is consumed in memory and
never played. Raw media, landmarks, transcripts, URLs, and credentials are not printed or
persisted. Hard deadlines and zero retries cap use at 1 Gemini realtime session. Headless
mode makes 0 `list_rooms` calls and 1 cleanup `delete_room` request; room, worker process
tree, and temporary WAV cleanup is attempted on success or failure. A cleanup failure makes
an otherwise successful smoke report fail.

A green headless result proves current service connectivity, named dispatch, media/data
transport, Gemini audio output, and halt/resume plumbing. It does not prove body-specific
pose accuracy, camera angle/lighting quality, resume authorization, or proactive Gemini
consumption of every tracking transition. Real camera validation remains separate.

## Next steps

- Add protocols only after MediaPipe thresholds and camera-view requirements are validated.
