I am implementing the "Session History" and Authentication layer for FlexFlow using Supabase and Next.js 15.
Please implement this in 4 distinct phases. Stop after each phase to allow me to review.

### Global Constraints
- **Styling:** Use `design_tokens.json` for all colors (`slate-900`, `emerald-500`) and spacing.
- **Privacy:** NEVER store raw user transcripts or video.
- **Strict Typing:** Use TypeScript for all Supabase database rows.

---

### Phase 1: Supabase Setup & Auth
1. **Install:** `npm install @supabase/ssr @supabase/supabase-js`.
2. **Utils:** Create standard Next.js 15 SSR clients:
   - `utils/supabase/server.ts` (Cookie-based client)
   - `utils/supabase/client.ts` (Browser client)
   - `utils/supabase/middleware.ts` (Session refresher)
3. **Middleware:** Create `middleware.ts` in the root.
   - It must refresh the Auth Session on every request.
   - **Protect Routes:** Redirect unauthenticated users from `/dashboard` and `/session` to `/login`.
4. **Login Page:** Create `app/login/page.tsx`.
   - **Design:** Use the "Clinical Studio" dark theme. Center a clean card on a `slate-950` background.
   - **Functionality:** Email/Password login + Sign Up toggle.
   - **Redirect:** On success, go to `/dashboard`.

---

### Phase 2: The "End Session" API Logic
Create a Route Handler at `app/api/save-session/route.ts`.
- **Input:** POST request with `{ transcript: Message[], duration: number }`.
- **Process:**
  1. **Auth Check:** Verify user with `supabase.auth.getUser()`. Return 401 if missing.
  2. **AI Analysis:** Send the `transcript` to Gemini 2.0 Flash.
     - **System Prompt:** "You are an expert Physical Therapist. Summarize this session. Return JSON ONLY with keys: `summary_text` (3-4 sentences), `pain_points` (array of strings), `stretches_performed` (array of strings), and `Youtube_queries` (3 specific search terms for their issues)."
     - **Config:** Set `response_mime_type: "application/json"`.
  3. **Resource Generation:** Transform `Youtube_queries` into clickable URLs: `https://www.youtube.com/results?search_query={encoded_term}`.
  4. **Database Insert:** Insert the summary and generated links into the `session_summaries` table.
  5. **Privacy Action:** Explicitly discard the `transcript` variable. Do not save it.

---

### Phase 3: The User Dashboard
Create `app/dashboard/page.tsx`.
- **Data Fetching:** Server Component. Fetch `session_summaries` ordered by `created_at` descending.
- **UI Layout:**
  - **Header:** "Your Recovery Journey" (White, Bold).
  - **Grid:** A generic grid of "Session Cards".
- **Session Card Design:**
  - **Top:** Date (e.g., "Feb 8") and Duration (e.g., "14 mins") in `text-slate-400`.
  - **Middle:** The AI Summary text (White).
  - **Tags:** Render `pain_points` as Rose-500 badges and `stretches_performed` as Emerald-500 badges.
  - **Footer:** "Recommended Resources" -> List of external links to YouTube.

---

### Phase 4: Frontend Integration
1. **Update Header:** Add a "Dashboard" link and a "Sign Out" button (using `supabase.auth.signOut()`) to the main app header.
2. **Connect 'End Session':** In the main `Session.tsx` component:
   - When the user clicks the Red "End Session" button, stop the tracks.
   - **POST** the current transcript to `/api/save-session`.
   - Show a "Generating Summary..." loading state.
   - On success, `router.push('/dashboard')`.

Start with Phase 1.