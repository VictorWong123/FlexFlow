"""
FlexFlow agent entrypoint: Gemini 2.5 Flash Native Audio (Live API) with
real-time vision via MediaPipe, exercise visual aids, and get_body_metrics tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RunContext, function_tool, room_io
from livekit.plugins import google, silero

from app.pain_guardrail import SAFETY_WARNING, check_pain_keywords
from app.services.exercise_db import search_exercise, search_exercises
from app.state import AsyncState
from app.utils.resources import (
    get_resource,
    list_resource_ids,
    search_static_resources,
)
from app.vision import VisionManager

logger = logging.getLogger("flexflow.agent")

load_dotenv(".env.local")
load_dotenv()

FLEXFLOW_SYSTEM_PROMPT = """\
You are Sewina, a warm, encouraging AI Physical Therapist assistant. You can see \
the user through their camera and hear them in real time. You are their coach — \
you decide the exercise plan, watch their form continuously, and correct them \
the moment something is off. Think of yourself as a real PT standing right next to them.

How to talk:
- Speak naturally, like a friendly coach standing next to them. Short sentences.
- Never list bullet points out loud. Just talk like a person.
- Give ONE cue at a time. Wait for them to adjust before adding another.
- Use encouraging words: "nice", "good", "that's it", "almost there."
- Don't repeat yourself or re-explain unless asked.

How to observe — THIS IS YOUR MOST IMPORTANT JOB:
- You MUST watch the user continuously while they exercise. Do NOT wait for them \
to ask "am I doing it right?" — you should already be telling them.
- The moment you see incorrect form, SAY SOMETHING IMMEDIATELY. Interrupt yourself \
if you have to. Examples: "Hold on — straighten your back." "Wait, your elbow is \
drifting out." "Stop — drop your shoulder down first."
- Use get_body_metrics frequently while the user is moving to verify joint angles.
- Be specific about what you see: "I can see your right elbow is at about 45 degrees — \
try to get it closer to 90."
- When form is good, confirm it: "Yes, that's the right position. Hold that."
- Think of it like spotting someone at the gym — you watch every rep, not just \
when they ask for help.

Leading the session — YOU are the therapist:
- After assessing the user's issue, YOU prescribe the exercise plan. You are the expert.
- If the user starts doing a different exercise on their own, do NOT just go along \
with it. Redirect them: "Hey, let's come back to the neck stretch — that's what's \
going to help your shoulders the most right now."
- Explain WHY your prescribed exercise matters: "I know the arm circles feel natural, \
but the cross-body stretch targets the exact area that's tight."
- Only switch exercises if: (1) the user explicitly asks to change, (2) the current \
exercise is causing pain, or (3) they've completed the prescribed sets/duration.
- Count reps if doing a repetitive exercise. Track their progress through the set.
- When one exercise is done, tell them what's next: "Nice work. Now let's move on to..."

Visual Aids:
- You have access to a database of 870+ exercises with images. Before recommending \
an exercise, call suggest_exercises with the target body area or movement, then \
pick ONE of the returned names and use that exact name when calling \
show_exercise_visuals. This guarantees the visuals match the recommendation.
- EVERY TIME you suggest a new exercise or stretch, call show_exercise_visuals with \
the exact database exercise name so the user sees images and step-by-step instructions.
- For common stretches (neck, shoulder, arm), you can also call show_exercise_resource \
with a stretch ID for curated professional videos. Available IDs: neck_lateral_flexion, \
neck_rotation, upper_trap_stretch, shoulder_cross_body, shoulder_overhead, chest_opener, \
bicep_stretch, tricep_stretch, wrist_flexor_stretch, cat_cow.
- Always show a visual reference when starting a new movement.

Safety:
- You're AI, not a doctor. Weave this in naturally once near the start: "Just a \
reminder, I'm AI — if anything feels sharp or wrong, stop and see a professional."
- Sharp pain, numbness, tingling, or dizziness → stop immediately, recommend a doctor.
- Normal workout discomfort (burn, tightness) → "Ease up if that's more than a 5 out of 10."

Never repeat or echo back what the user says."""


class FlexFlowAgent(Agent):
    """Voice + vision agent backed by Gemini 2.5 Flash (Live API)."""

    def __init__(self, state: AsyncState, room: Any) -> None:
        super().__init__(instructions=FLEXFLOW_SYSTEM_PROMPT)
        self._state = state
        self._room = room

    async def _publish_exercise(self, data: dict[str, Any]) -> None:
        """Publish exercise data to the frontend via LiveKit data channel."""
        try:
            payload = json.dumps(data).encode("utf-8")
            await self._room.local_participant.publish_data(
                payload, reliable=True, topic="exercise"
            )
        except Exception:
            logger.exception("Failed to publish exercise data")

    @function_tool()
    async def get_body_metrics(self, context: RunContext) -> dict[str, object]:
        """
        Get current body metrics from the vision system. Returns neck angle,
        arm angles, upper-body-only mode, and pointed body part. Call this
        to verify the user's form before giving corrections.
        """
        return await self._state.snapshot()

    @function_tool()
    async def show_exercise_resource(
        self, context: RunContext, stretch_id: str
    ) -> dict[str, object]:
        """
        Show the user a curated professional video and thumbnail for a common
        stretch. Use this for well-known stretches. Available stretch IDs:
        neck_lateral_flexion, neck_rotation, upper_trap_stretch,
        shoulder_cross_body, shoulder_overhead, chest_opener,
        bicep_stretch, tricep_stretch, wrist_flexor_stretch, cat_cow.
        """
        resource = get_resource(stretch_id)
        if resource is None:
            return {
                "status": "not_found",
                "message": f"No resource found for '{stretch_id}'.",
                "available_ids": list_resource_ids(),
            }

        exercise_data = {
            "type": "SHOW_RESOURCE",
            "title": resource.title,
            "image_url": resource.thumbnail_url,
            "youtube_url": resource.youtube_embed_url,
            "body_part": resource.body_part,
            "instructions": [resource.description],
        }
        await self._publish_exercise(exercise_data)
        return {
            "status": "shown",
            "title": resource.title,
            "description": resource.description,
        }

    @function_tool()
    async def suggest_exercises(
        self, context: RunContext, query: str
    ) -> dict[str, object]:
        """
        Return a short list of exercise names that best match a query.
        Use this to pick an exact database name before recommending.
        """
        results = await search_exercises(query, limit=5)
        return {
            "status": "ok",
            "query": query,
            "results": [r.get("name", "") for r in results if r.get("name")],
        }

    @function_tool()
    async def show_exercise_visuals(
        self, context: RunContext, exercise_name: str
    ) -> dict[str, object]:
        """
        Search for an exercise by name and show the user images with
        step-by-step instructions on screen. Uses a database of 870+
        exercises, all with images. Call this EVERY TIME you recommend a
        new movement so the user has a visual reference.
        """
        result = await search_exercise(exercise_name)

        if result is None:
            static = search_static_resources(exercise_name)
            if static is not None:
                exercise_data = {
                    "type": "SHOW_RESOURCE",
                    "title": static.title,
                    "image_url": static.thumbnail_url,
                    "youtube_url": static.youtube_embed_url,
                    "body_part": static.body_part,
                    "instructions": [static.description],
                }
                await self._publish_exercise(exercise_data)
                return {
                    "status": "shown",
                    "source": "static",
                    "title": static.title,
                    "description": static.description,
                }
            return {
                "status": "not_found",
                "message": f"No exercise found for '{exercise_name}'.",
            }

        youtube_url = ""
        static = search_static_resources(exercise_name)
        if static is not None:
            youtube_url = static.youtube_embed_url

        exercise_data = {
            "type": "SHOW_EXERCISE",
            "title": result["name"],
            "image_url": result.get("image_url", ""),
            "image_url_end": result.get("image_url_end", ""),
            "youtube_url": youtube_url,
            "body_part": ", ".join(result.get("primary_muscles", [])),
            "equipment": result.get("equipment", ""),
            "instructions": result.get("instructions", []),
        }
        await self._publish_exercise(exercise_data)
        return {
            "status": "shown",
            "source": "free_exercise_db",
            "title": result["name"],
            "instructions": result.get("instructions", []),
        }


def should_trigger_pain_guardrail(transcript: str) -> bool:
    return check_pain_keywords(transcript)


def get_pain_safety_instruction() -> str:
    return SAFETY_WARNING


_server = agents.AgentServer()


def _prewarm(proc: agents.JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


_server.setup_fnc = _prewarm


@_server.rtc_session()
async def _flexflow_session(ctx: agents.JobContext) -> None:
    """One shared state per room; vision loop feeds body metrics to the agent."""
    state = AsyncState()
    agent = FlexFlowAgent(state=state, room=ctx.room)

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            voice="Puck",
            temperature=0.4,
            proactivity=True,
            enable_affective_dialog=True,
        ),
        vad=ctx.proc.userdata["vad"],
    )

    vision_task: asyncio.Task[None] | None = None

    @ctx.room.on("track_subscribed")
    def _on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        nonlocal vision_task
        if track.kind != rtc.TrackKind.KIND_VIDEO:
            return
        if vision_task is not None and not vision_task.done():
            vision_task.cancel()
        mgr = VisionManager(track, state, ctx.room.local_participant)
        vision_task = asyncio.create_task(mgr.run())
        logger.info("VisionManager started for %s", participant.identity)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(video_input=True),
    )
    await ctx.connect()
    await session.generate_reply(
        instructions="Greet the user warmly and briefly. Let them know you can see them. Ask what they'd like to work on today."
    )


def run_app() -> None:
    """Run the LiveKit agent (dev | start | console)."""
    agents.cli.run_app(_server)


if __name__ == "__main__":
    run_app()
