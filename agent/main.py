"""LiveKit Agents entry point for the meeting interpreter.

Run with:  python -m agent.main dev   (local development, see README)
Deployment: start this module as a LiveKit Cloud agent worker.

Dispatch contract: the web token endpoint creates an agent dispatch whose
``agent_name`` matches ``AGENT_NAME`` below and whose ``metadata`` carries the
room's language pair (``{"pair": "bn-en"}``); LiveKit then starts this worker
for the room and it is shared by every participant in that room.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli  # noqa: E402

from .config import DEFAULT_AGENT_NAME, load_config  # noqa: E402
from .routing import DEFAULT_PAIR, LanguagePair, pair_from_metadata  # noqa: E402
from .session import InterpreterManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("interpreter")

AGENT_NAME = os.getenv("AGENT_NAME", "").strip() or DEFAULT_AGENT_NAME

server = AgentServer()


def _prewarm_http_ssl_context() -> None:
    """Build LiveKit's shared HTTP SSL context before the event loop needs it.

    livekit-agents creates the context lazily on the first HTTP use (the inference
    plugins call ``http_context.http_session()`` from their constructor) and caches
    it process-wide via ``functools.cache``. On Windows, building a default context
    enumerates the system certificate store and costs ~200-300ms, which lands on the
    event loop and blocks audio/turn handling ("event loop blocked ... in
    create_default_context"). Warming the cache here - and, in ``entrypoint``, in a
    worker thread - moves that cost off the loop.

    Uses framework internals defensively: if they are renamed, prewarming is skipped
    and behavior degrades to the previous lazy path.
    """
    try:
        from livekit.agents.utils import http_context
    except Exception:  # noqa: BLE001 - prewarming is best-effort
        return
    try:
        set_cert_env = getattr(http_context, "_set_default_cert_env", None)
        if callable(set_cert_env):
            set_cert_env()
        create_ctx = getattr(http_context, "_create_ssl_context", None)
        if callable(create_ctx):
            create_ctx()
    except Exception:  # noqa: BLE001 - never fail startup over a warmup
        logger.debug("HTTP SSL context prewarm failed", exc_info=True)


def _room_pair(ctx: JobContext) -> LanguagePair:
    """Resolve the room's language pair from dispatch or room metadata.

    The dispatch metadata set by the token endpoint takes precedence; room metadata
    is used as a fallback so the pair is stable across worker restarts.
    """
    for source, value in (
        ("dispatch", getattr(ctx.job, "metadata", None)),
        ("room", getattr(ctx.room, "metadata", None)),
    ):
        pair = pair_from_metadata(value)
        if pair != DEFAULT_PAIR:
            logger.info("using language pair %s from %s metadata", pair.code, source)
            return pair
    return DEFAULT_PAIR


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    # Job processes run inference sessions on this loop; warm the shared HTTP TLS
    # context in a thread first so the first inference connection does not block it.
    await asyncio.to_thread(_prewarm_http_ssl_context)

    config = load_config()  # raises ConfigError with variable names only
    ctx.log_context_fields = {"room": ctx.room.name}

    pair = _room_pair(ctx)
    manager = InterpreterManager(ctx, config, pair)
    manager.start()

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    for participant in list(ctx.room.remote_participants.values()):
        manager.on_participant_connected(participant)

    async def cleanup() -> None:
        await manager.aclose()

    ctx.add_shutdown_callback(cleanup)
    logger.info("interpreter agent ready in room %r (pair=%s)", ctx.room.name, pair.code)


def main() -> None:
    load_dotenv()
    try:
        load_config()
    except Exception as exc:  # noqa: BLE001 - fail fast with a clear, safe message
        raise SystemExit(f"Configuration error: {exc}") from exc
    _prewarm_http_ssl_context()  # before the loop starts: worker HTTP session setup
    cli.run_app(server)


if __name__ == "__main__":
    main()
