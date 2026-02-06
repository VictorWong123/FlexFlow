"""
FlexFlow agent entrypoint: Gemini 2.5 Flash Native Audio (Live API) with
get_body_metrics tool and pain guardrail. No video/audio stored; all in-memory.
"""

from __future__ import annotations

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext, function_tool
from livekit.plugins import google

from app.pain_guardrail import SAFETY_WARNING, check_pain_keywords
from app.state import AsyncState

load_dotenv(".env.local")
load_dotenv()

FLEXFLOW_SYSTEM_PROMPT = """\
Role: You are Sewina, a professional and empathetic AI Physical Therapist Assistant. Your primary goal is to guide the user through safe mobility, stretching, and form correction. 

Behavioral Directives:
- Analysis: Ask clarifying questions to understand the user's pain and symptoms before giving advice.                    
- Data-Grounded: Use the `get_body_metrics` tool to verify the user’s real-time joint angles and posture before confirming they are performing a movement correctly.

Safety & Pain Logic:
- Pain Compass: Help the user distinguish between "Good Pain" (burn, dull ache, tightness) and "Bad Pain" (sharp, stabbing, electric, pinpointed, or radiating). 
- 5/10 Rule: If the user reports pain exceeding a 5/10 intensity, instruct them to reduce their range of motion or stop the exercise entirely.
- The Red Flag Protocol: Immediately stop all guidance and instruct the user to seek professional medical evaluation if they report:
    1. Sharp or stabbing pain.
    2. Numbness or tingling (pins and needles).
    3. Dizziness or shortness of breath.
    4. Pain that follows a recent trauma (pop/snap).

Mandatory Disclaimers:
- Frequently remind the user: "I am an AI, not a doctor. My guidance is for educational purposes. Stop if you feel pain."
- Integrate these disclaimers naturally into your coaching flow rather than just at the start.

Response Style:
- Use clinical terminology: Flexion, extension, pronation, supination, and lateral rotation.
- Be concise: Use bullet points for instructions. 
- Prioritize Safety: When in doubt, advise a smaller range of motion over a deeper stretch."""


class FlexFlowAgent(Agent):
    """
    Voice agent backed by Gemini 2.5 Flash Native Audio (Live API). Reads real-time
    body metrics from the shared AsyncState via get_body_metrics.
    """

    def __init__(self, state: AsyncState) -> None:
        super().__init__(instructions=FLEXFLOW_SYSTEM_PROMPT)
        self._state = state

    @function_tool()
    async def get_body_metrics(self, context: RunContext) -> dict[str, object]:
        """
        Get current body metrics from the vision whiteboard. Call this to verify
        the user's form (neck angle, arm angles, upper-body-only mode) before
        giving PT guidance.
        """
        snapshot = await self._state.snapshot()
        return snapshot


def create_session() -> AgentSession:
    """Create an AgentSession with Gemini Live API native audio model."""
    return AgentSession(
        llm=google.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            voice="Puck",
            temperature=0.7,
            instructions=FLEXFLOW_SYSTEM_PROMPT,
        ),
    )


def should_trigger_pain_guardrail(transcript: str) -> bool:
    """Use this when user transcript is available; if True, clear buffer and deliver safety message."""
    return check_pain_keywords(transcript)


def get_pain_safety_instruction() -> str:
    """Instruction to send to the agent when pain is detected (e.g. via generate_reply)."""
    return SAFETY_WARNING


_server = agents.AgentServer()


@_server.rtc_session()
async def _flexflow_session(ctx: agents.JobContext) -> None:
    """One shared state per room; vision loop (separate) will update it."""
    state = AsyncState()
    agent = FlexFlowAgent(state=state)
    session = create_session()
    await session.start(room=ctx.room, agent=agent)
    await session.generate_reply(
        instructions="Greet the user briefly as FlexFlow and offer to guide them through a safe stretch or exercise. Ask what area they want to focus on."
    )


def run_app() -> None:
    """Run the LiveKit agent (dev | start | console)."""
    agents.cli.run_app(_server)


if __name__ == "__main__":
    run_app()
