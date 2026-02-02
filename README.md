# FlexFlow Backend

Real-time AI Physical Therapist backend: FastAPI + LiveKit Agents + Gemini 2.0 Flash (Multimodal Live API). Vision math uses MediaPipe Holistic; all processing is **in-memory** (no video/audio stored).

## Requirements

- **Python 3.10+**
- LiveKit Cloud (or self-hosted) and Google Gemini API key

## Setup

```bash
# Create venv and install
python3.10 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Copy env and set keys (no keys in repo)
cp .env.example .env.local
# Edit .env.local: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, GOOGLE_API_KEY
```

## Run

- **HTTP server (health/ready):**
  ```bash
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
  ```

- **LiveKit agent (dev / start / console):**
  ```bash
  uv run python -m app.agent dev    # or: start | console
  ```
  Or: `python -m app.agent dev` after activating the venv.

## Layout

| Path | Role |
|------|------|
| `main.py` | FastAPI app (health, ready) |
| `app/agent.py` | FlexFlow agent entrypoint; Gemini realtime, `get_body_metrics`, pain guardrail |
| `app/state.py` | Shared `AsyncState` (whiteboard): `is_upper_body_only`, `neck_angle`, `arm_angles`, `pointed_body_part` |
| `app/utils/physics.py` | Vision math: neck tilt, elbow flexion (MediaPipe landmarks) |
| `app/pain_guardrail.py` | Pain keywords and safety message |

## Pain guardrail

When user transcript contains `ouch`, `hurts`, `pain`, or `stop`, call `should_trigger_pain_guardrail(transcript)`; if `True`, clear speech buffer and deliver `get_pain_safety_instruction()` (e.g. via `session.generate_reply(instructions=...)`).

## Next steps

- Implement the **adaptive vision loop**: MediaPipe Holistic on user video track, landmarks 0–33, upper-body mode when 25–32 visibility &lt; 0.5, and write neck/arm angles into `AsyncState`.
- Wire the pain guardrail to the realtime transcript stream.
