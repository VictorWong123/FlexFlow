"""
FlexFlow agent entrypoint: Gemini 2.0 Flash (Multimodal Live API) with
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
You are FlexFlow, a supportive AI Physical Therapist. \
Use the get_body_metrics tool to verify the user's form when giving exercise guidance. \
If the user mentions pain, stop immediately and advise them to consult a healthcare provider. \
You are not a doctor; prioritize safety."""


class FlexFlowAgent(Agent):
    """
    Voice agent backed by Gemini 2.0 Flash (Multimodal Live). Reads real-time
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
    """Create an AgentSession with Gemini 2.0 Flash realtime model."""
    return AgentSession(
        llm=google.realtime.RealtimeModel(
            model="gemini-2.0-flash-exp",  # Gemini 2.0 Flash Multimodal Live API
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


# ---------------------------------------------------------------------------
# LiveKit agent server (entrypoint: uv run app.agent dev | start | console)
# ---------------------------------------------------------------------------

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
    # When transcript is available (e.g. from realtime model or STT), call:
    #   if should_trigger_pain_guardrail(transcript):
    #     await session.generate_reply(instructions=get_pain_safety_instruction())


def run_app() -> None:
    """Run the LiveKit agent (dev | start | console)."""
    agents.cli.run_app(_server)


if __name__ == "__main__":
    run_app()
