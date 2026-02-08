I want to add visual aids (YouTube videos and images) to FlexFlow.

### Task:
1. Create `app/utils/resources.py` with a dictionary mapping stretch IDs to YouTube Embed URLs and GIF links for Neck, Shoulder, and Arm stretches.
2. In `agent.py`, implement a LiveKit Tool called `show_exercise_resource(stretch_id)`.
3. I want a dynamic integration using the ExerciseDB API via RapidAPI.
4. Update the AI's System Prompt to ensure it calls this tool every time it suggests a new movement.

### Frontend Requirement (Next.js):
- Create a `VisualAids` component in the React frontend that listens for the 'SHOW_RESOURCE' data channel event.
- When it receives data, it should display a modal or a side-panel containing the YouTube iframe and the exercise title.

Follow the rules in .cursor/rules/standards.mdc. Use professional PT videos for the initial resource map.



### Requirements:
1. Create `app/services/exercise_db.py` using `httpx` to search for exercises by name.
2. Ensure it pulls the `gifUrl`, `name`, and `instructions` from the ExerciseDB response.
3. In `agent.py`, implement the `show_exercise_visuals` tool.
4. Update the System Prompt: "You have access to a massive database of 1,300+ exercises. When recommending a movement, search for it by name using `show_exercise_visuals` to provide the user with a GIF and step-by-step instructions."
5. Frontend: Update the React UI to catch the `SHOW_EXERCISE` event and display the GIF in a clean, professional modal.

Follow .cursor/rules/standards.mdc and ensure API keys are pulled from environment variables.