# FlexFlow Frontend

Next.js frontend for FlexFlow AI Physical Therapist. Built with React, TypeScript, and Tailwind CSS.

## Setup

```bash
cd frontend
npm install
```

Copy `.env.example` to `.env.local` and set:

- `NEXT_PUBLIC_LIVEKIT_URL` – LiveKit WebRTC URL
- `NEXT_PUBLIC_API_URL` – Backend API URL (e.g. `http://localhost:8000`)

## How to Run

Use **3 terminals** (backend, agent, then frontend):

**Terminal 1 – Backend:**
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

Open [http://localhost:3000](http://localhost:3000).

## Structure

- `app/` – Next.js App Router pages and layouts
- `components/` – React components (e.g. VideoSession)
