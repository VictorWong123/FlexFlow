# FlexFlow Vision System Specification

## Overview
This module (`app/vision.py`) acts as the "eyes" of the AI Physical Therapist. It consumes a real-time LiveKit video track, processes it with MediaPipe Holistic, and updates the shared `AsyncState` with body metrics.

## Architecture

### 1. VisionManager Class
**Location:** `app/vision.py`
**Dependencies:** `livekit`, `mediapipe`, `asyncio`, `app.state`, `app.utils.physics`

#### Core Responsibilities:
- **Input:** Accepts a `livekit.rtc.VideoTrack`.
- **Stream:** Uses `livekit.rtc.VideoStream` to get frames asynchronously.
- **Concurrency:** MUST run MediaPipe `process()` calls in a `concurrent.futures.ThreadPoolExecutor` to avoid blocking the main asyncio event loop (which handles audio).

### 2. Processing Logic
For every frame, extract `pose_landmarks` and perform the following analysis:

#### A. Adaptive Body Mode
- **Logic:** Check visibility of "Lower Body" landmarks (Indices 25-32: Hips, Knees, Ankles).
- **Threshold:** If visibility < 0.5 for knees/ankles, set `state.is_upper_body_only = True`.
- **Output:** Update `AsyncState`.

#### B. Pointing Detection (User Intent)
- **Goal:** Detect if the user is pointing at a specific body part to indicate pain.
- **Algorithm:** Calculate Euclidean Distance between **Index Finger Tip (Landmark 8)** and target joints (Shoulders, Elbows, Knees).
- **Threshold:** If distance < 0.1 (normalized coordinate space), consider it a "Point".
- **Priority:** Map the closest joint to `state.pointed_body_part` (e.g., "Right Shoulder").

#### C. Metrics Calculation
- Use `app/utils/physics.py` to calculate:
  - `neck_angle`: Nose (0) relative to Shoulder Midpoint.
  - `arm_flexion`: Left/Right elbow angles.
- **Smoothing:** (Optional) Implement a simple moving average (buffer size=5) to prevent jitter in the LLM's data feed.

### 3. Safety & Performance
- **Zero-Storage:** Do not save images to disk. Process in memory only.
- **Error Handling:** If `track` is muted or frames are empty, sleep briefly (`0.1s`) and retry. Do not crash.
- **Resource Management:** Implement a `close()` method to shut down the thread pool and release MediaPipe resources.

## Integration Plan
- In `agent.py`, listen for `TrackSubscribed` events.
- If `kind == Video`, initialize `VisionManager` and start its loop as a background task.