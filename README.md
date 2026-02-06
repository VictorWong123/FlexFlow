# FlexFlow

Real-time AI Physical Therapist: FastAPI backend + LiveKit Agents + Gemini 2.0 Flash (Multimodal Live API). Vision math uses MediaPipe Holistic; all processing is **in-memory** (no video/audio stored).

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
# Add: NEXT_PUBLIC_LIVEKIT_URL, NEXT_PUBLIC_API_URL
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
| `backend/app/state.py` | Shared `AsyncState` (whiteboard) |
| `backend/app/utils/physics.py` | Vision math: neck tilt, elbow flexion |
| `backend/app/pain_guardrail.py` | Pain keywords and safety message |

## Why do I need a Gemini API key? Doesn’t LiveKit run the LLM?

**LiveKit and Gemini do different jobs.**

- **LiveKit** (your `LIVEKIT_*` keys) runs the **real-time layer**: rooms, WebRTC, media (audio/video), and agent dispatch. It does **not** run or host Gemini. It doesn’t substitute for a Google API key.

- **Gemini** (your `GOOGLE_API_KEY`) runs the **model**: understanding, reasoning, and voice (the “AI” that follows instructions and uses `get_body_metrics`). Your FlexFlow worker calls **Google’s Gemini API** (e.g. Multimodal Live) from your backend; that call is authenticated with `GOOGLE_API_KEY`.

So: LiveKit = transport and orchestration; Gemini = the actual LLM/voice. You need both keys. LiveKit cannot “use Gemini for you” without you providing a Gemini API key, because the model always runs on Google’s side and is billed/authenticated via your Google Cloud / Gemini API key.

## Pain guardrail

When user transcript contains `ouch`, `hurts`, `pain`, or `stop`, call `should_trigger_pain_guardrail(transcript)`; if `True`, clear speech buffer and deliver `get_pain_safety_instruction()` (e.g. via `session.generate_reply(instructions=...)`).

## Frontend

The frontend is a Next.js app with React and Tailwind CSS. See `frontend/README.md` for setup.

```bash
cd frontend
npm install
npm run dev
```

## Next steps

- Implement backend token endpoint for LiveKit access tokens (frontend needs this to connect)
- Implement the **adaptive vision loop**: MediaPipe Holistic on user video track, landmarks 0–33, upper-body mode when 25–32 visibility &lt; 0.5, and write neck/arm angles into `AsyncState`.
- Wire the pain guardrail to the realtime transcript stream.
