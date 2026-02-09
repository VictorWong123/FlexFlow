# FlexFlow - AI Physical Therapist in Your Browser

## Inspiration

Physical therapy is expensive, inconvenient, and hard to access. A single session can cost $75-$200, and most people can't justify that for minor aches and pains from sitting at a desk all day. We've all been there — neck tension from coding marathons, shoulder stiffness from poor posture, wrist pain from endless typing. You know you should stretch, but without real-time feedback, you have no idea if you're doing it right or making it worse.

We built FlexFlow to democratize physical therapy. Imagine having a professional PT watching your form in real-time, correcting you the moment you make a mistake, and tracking your recovery progress — all for free, right in your browser, with no appointments and no waiting rooms.

## What it does

FlexFlow is a **real-time AI Physical Therapist** that uses your webcam to analyze your movement, correct your form instantly, and guide you through personalized stretches and exercises.

**Core Features:**

1. **Real-Time Vision & Form Correction**
   - Uses MediaPipe to track 33 3D body landmarks (x, y, z coordinates + visibility scores)
   - Calculates joint angles, posture alignment, and movement patterns in real-time
   - The AI *watches you continuously* and interrupts mid-exercise if your form is wrong
   - Gives specific corrections: "Drop your right shoulder," "Straighten your back," "Tilt further to the left"

2. **Multimodal Conversation**
   - Powered by Google Gemini 2.5 Flash's Multimodal Live API (native audio + video)
   - Natural voice conversation — just talk to it like a real PT
   - The AI sees your camera feed directly and responds to what it observes, not just what you say

3. **Exercise Visual Library**
   - Database of 870+ exercises with start/end position images and step-by-step instructions
   - Sophisticated search algorithm (synonyms, muscle-group matching, category boosting)
   - Displays professional exercise images and YouTube tutorials on-screen during your session

4. **AI Session Summaries & Progress Tracking**
   - At the end of each session, Gemini analyzes your transcript and generates a medical-grade summary
   - Extracts pain points, stretches performed, and recommended YouTube resources
   - All saved to your personal dashboard with full authentication (Supabase)
   - Track your recovery journey over time

5. **Privacy-First Design**
   - All vision processing happens in real-time memory — no video recording
   - Audio is streamed, not saved — no raw audio files stored
   - Transcripts are discarded after generating the AI summary
   - Your health data is yours alone

## How we built it

**Tech Stack:**

- **Frontend:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Framer Motion, LiveKit Client SDK
- **Backend:** Python 3.10+, FastAPI, LiveKit Agents Framework, MediaPipe Pose (Tasks API), OpenCV
- **AI/ML:** Google Gemini 2.5 Flash (Multimodal Live API for real-time sessions, REST API for summaries), Silero VAD
- **Real-time Communication:** LiveKit (WebRTC, data channels for landmark streaming and exercise images)
- **Database & Auth:** Supabase (PostgreSQL + Row Level Security)
- **Exercise Data:** Free Exercise Database (GitHub, 870+ exercises with images)

**Architecture:**

1. **Frontend (Next.js)**
   - `VideoSession` component establishes WebRTC connection to LiveKit
   - Publishes user's camera + microphone to the room
   - Subscribes to agent's audio track (AI voice responses)
   - Listens on data channels for: (a) pose landmarks for body mode chip, (b) exercise data for visual cards
   - Displays live transcript, exercise images/instructions, and push-to-talk controls

2. **Backend Agent (LiveKit + Gemini)**
   - LiveKit agent joins the room when a participant connects
   - `VisionManager` subscribes to user's video track, runs MediaPipe Pose frame-by-frame
   - Extracts 3D landmarks, computes metrics (neck angle, arm angles, upper/full body mode)
   - Stores metrics in shared `AsyncState`, publishes landmarks to frontend via data channel
   - `AgentSession` connects to Gemini 2.5 Flash Realtime API with Silero VAD
   - Agent uses tools: `get_body_metrics` (checks form), `suggest_exercises` (searches DB), `show_exercise_visuals` (displays images)

3. **Exercise Search System**
   - On first call, downloads `exercises.json` from GitHub (870+ exercises) and caches in memory
   - Custom fuzzy search with:
     - Synonym expansion ("trapezius" → "traps")
     - Name matching (exact > substring > word overlap)
     - Muscle-group matching (primary muscles score higher)
     - Category boosting (prefer "stretching" if query contains "stretch")
     - Generic word filtering and cross-validation penalties
   - Returns start/end position images (GitHub CDN), instructions, and YouTube tutorials

4. **Session Summary Pipeline**
   - User clicks "End Session" → frontend captures final transcript lines (speaker, text)
   - POSTs to `/api/save-session` with transcript + duration
   - Server-side route calls Gemini 2.5 Flash (REST API) with prompt: "Summarize this PT session as JSON"
   - Gemini extracts: `summary_text`, `pain_points`, `stretches_performed`, `youtube_queries`
   - Transforms YouTube queries into search URLs, inserts into Supabase with RLS
   - Transcript is discarded — never stored

5. **Authentication & Dashboard**
   - Supabase SSR with Next.js middleware (cookie-based sessions)
   - Protected routes: `/dashboard`, `/dashboard/[id]`
   - Dashboard shows session cards (date, duration, truncated summary, tags)
   - Detail page shows full summary, pain points, stretches, YouTube resources, and delete option

## Challenges we ran into

**1. Exercise Image Sourcing**
   - **Problem:** RapidAPI's ExerciseDB free tier didn't provide image URLs (`gifUrl` was always null). Even direct image links were blocked by hotlinking protection.
   - **Solution:** Switched to the free-exercise-db from GitHub (870+ exercises, all with images). Built a custom caching layer and sophisticated fuzzy search to ensure relevant matches.

**2. Real-Time Vision Integration**
   - **Problem:** MediaPipe has two APIs (Solutions API is deprecated, Tasks API is bleeding-edge). The Tasks API uses `await` for async processing, which doesn't play well with real-time video frame loops.
   - **Solution:** Wrapped MediaPipe's async `detect_async` in a thread-safe queue. Each frame is processed asynchronously but results are consumed by the agent synchronously via shared state.

**3. Session Summary Race Condition**
   - **Problem:** When the user clicked "End Session," the frontend disconnected from the room, which fired `RoomEvent.Disconnected`, which unmounted the entire component — aborting the POST request to `/api/save-session` before it completed.
   - **Solution:** Added an `endingRef` flag. When set to true, the disconnect event doesn't unmount the component, allowing the save request to complete. Only after the summary is saved and the user is redirected does the component unmount.

**4. Gemini API Quota Exhaustion**
   - **Problem:** The backend agent and the session summary route initially shared the same Google API key. Heavy testing burned through the free tier quota, breaking summaries with `limit: 0` errors.
   - **Solution:** Used separate API keys (different Google projects) for the live agent (Multimodal Live API) vs. session summaries (REST API). Also switched from `gemini-2.0-flash` to `gemini-2.5-flash` when the new key had zero 2.0 allocation.

**5. Next.js SSR + Supabase Auth**
   - **Problem:** Creating the Supabase client during Next.js prerendering caused build failures (`Invalid supabaseUrl` error) because `.env` placeholders were evaluated server-side.
   - **Solution:** Moved Supabase client initialization to form submission (client-side) for the login page and used Server Components with `cookies()` for protected routes. Added proper Suspense boundaries for `useSearchParams()`.

**6. Connection Latency (5+ seconds)**
   - **Problem:** The agent took 5-6 seconds to greet the user after joining the session.
   - **Solution:** Parallelized frontend mic/camera publishing with `Promise.all()` (~500ms saved) and reordered backend to call `ctx.connect()` BEFORE `session.start()` so the agent sees participants immediately (~1-2s saved). Remaining latency (~2-3s) is inherent to LiveKit Cloud dispatch + Gemini Realtime API connection.

## Accomplishments that we're proud of

1. **Real-Time Multimodal AI That Actually Works**
   - We built a *genuinely useful* AI health app, not a toy. The agent watches you, understands your form, and corrects you mid-exercise — that's the future of telehealth.

2. **End-to-End System in 48 Hours**
   - From concept to production: real-time vision, multimodal LLM, exercise search, authentication, session history, dashboard, and a polished UI. Every feature works seamlessly together.

3. **Privacy-First Architecture**
   - We could have taken shortcuts and stored raw video/audio for "debugging." Instead, we built a system that respects user privacy from day one — all processing is real-time, nothing is saved except AI-generated summaries.

4. **Sophisticated Exercise Search**
   - Our search algorithm isn't a naive string match. It understands synonyms ("traps" = "trapezius"), scores muscle-group relevance, boosts categories, and penalizes generic matches. It consistently returns the *right* exercise, not just *an* exercise.

5. **Clinical-Grade Design**
   - The UI isn't just pretty — it's purposeful. Every color, badge, and layout choice follows a consistent design system (`design_tokens.json`). The "Clinical Minimalism" landing page is a masterclass in professional web design.

## What we learned

**Technical:**
- How to integrate Google Gemini's Multimodal Live API with LiveKit for real-time audio+video streaming
- The intricacies of WebRTC data channels for low-latency metadata transport (landmarks, exercise images)
- MediaPipe's Tasks API for 3D pose estimation and the challenges of async processing in real-time loops
- Next.js 15's App Router + Supabase SSR patterns (Server Components, cookies, middleware, RLS)
- The importance of quota management when using multiple AI APIs (separating live vs. batch workloads)

**Product:**
- Real-time feedback is *everything* in a PT app. Without immediate corrections, users just follow along blindly and potentially hurt themselves.
- Visual aids (exercise images + videos) dramatically increase user confidence. Even if the AI explains the stretch perfectly, users still want to *see* it.
- Session summaries are the "aha moment" for retention. Users love seeing their pain points and stretches tagged and saved.

**Design:**
- Less is more. The landing page has zero icons, zero stock photos — just bold typography and a clear value prop. It's more impactful than any Dribbble-inspired design.
- Consistency matters. Using a design token system from day one saved us hours of "does this shade of gray match?"

## What's next for FlexFlow

**Short-Term (Post-Hackathon):**
1. **Exercise Plans & Routines**
   - Pre-built PT programs for common issues (e.g., "Desk Worker Recovery," "Posture Correction Week 1-4")
   - Progress tracking: reps, sets, duration over time
   - Reminders to stretch throughout the day

2. **Advanced Form Analysis**
   - Range-of-motion measurements (e.g., "Your neck rotation is 60° — aim for 80°")
   - Asymmetry detection (e.g., "Your left shoulder is 5° higher than your right")
   - Export reports as PDFs for doctor visits

3. **Multi-User & PT Dashboard**
   - PTs can create accounts, invite patients, and monitor their sessions remotely
   - Patients can share sessions with their real-world PT for review
   - HIPAA compliance for clinical use

**Long-Term (Product Vision):**
1. **Mobile App (React Native)**
   - Same backend, same AI, optimized for phone cameras
   - Phone can be propped up for full-body exercises (squats, lunges)

2. **Injury Prevention & Early Detection**
   - Train ML models on thousands of PT sessions to predict injury risk
   - Alert users: "Your posture shows signs of developing lower back pain — here's a prevention plan"

3. **Insurance Integration**
   - Partner with insurers to offer FlexFlow as a covered telehealth benefit
   - Reduce costs for insurers (FlexFlow sessions cost pennies vs. $100+ in-person visits)

4. **Multi-Language Support**
   - Gemini supports 100+ languages — internationalize to serve global users
   - Localize exercise names and instructions

5. **Hardware Integration**
   - Support for wearables (Apple Watch, Oura Ring) to track metrics over time
   - Smart home camera integration for better full-body tracking

**FlexFlow's Mission:**
Make professional physical therapy accessible to everyone, everywhere, for free. No appointments, no waiting rooms, no $200 bills. Just open your browser and get better.

---

**Try it live:** [Your demo link here]  
**GitHub:** [Your repo link here]  
**Built with:** LiveKit, Google Gemini 2.5 Flash, Next.js, Supabase, MediaPipe
