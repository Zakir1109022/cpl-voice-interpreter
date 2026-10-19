"""LiveKit Agents entry point for the Bengali <-> English meeting interpreter.

Run with:  python -m agent.main dev   (local development, see README)
Deployment: start this module as a LiveKit Cloud agent worker.

Dispatch contract: the web token endpoint creates an agent dispatch whose
``agent_name`` matches ``AGENT_NAME`` below; LiveKit then starts this worker
for the room and it is shared by every participant in that room.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli  # noqa: E402

from .config import DEFAULT_AGENT_NAME, load_config  # noqa: E402
from .session import InterpreterManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("interpreter")

AGENT_NAME = os.getenv("AGENT_NAME", "").strip() or DEFAULT_AGENT_NAME

server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    config = load_config()  # raises ConfigError with variable names only
    ctx.log_context_fields = {"room": ctx.room.name}

    manager = InterpreterManager(ctx, config)
    manager.start()

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    for participant in list(ctx.room.remote_participants.values()):
        manager.on_participant_connected(participant)

    async def cleanup() -> None:
        await manager.aclose()

    ctx.add_shutdown_callback(cleanup)
    logger.info("interpreter agent ready in room %r", ctx.room.name)


def main() -> None:
    load_dotenv()
    try:
        load_config()
    except Exception as exc:  # noqa: BLE001 - fail fast with a clear, safe message
        raise SystemExit(f"Configuration error: {exc}") from exc
    cli.run_app(server)


if __name__ == "__main__":
    main()
