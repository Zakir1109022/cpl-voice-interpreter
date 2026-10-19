"""Translation pipeline wiring: STT -> LLM -> TTS for one source language.

LiveKit-model construction lives here so routing/prompts stay pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from livekit.agents import NOT_GIVEN, Agent, AgentSession, inference

from .config import Config
from .native_compat import native_inference_available
from .prompts import translation_instructions
from .routing import DEFAULT_PAIR, LanguagePair, track_name_for


class TranslatorAgent(Agent):
    """Agent that only translates; it never answers or explains."""

    def __init__(self, *, source_language: str, target_language: str) -> None:
        super().__init__(
            instructions=translation_instructions(source_language, target_language)
        )
        self.source_language = source_language
        self.target_language = target_language


@dataclass(frozen=True)
class Direction:
    source_language: str
    target_language: str
    audio_track_name: str


def direction_for(
    source_language: str, pair: LanguagePair = DEFAULT_PAIR, config: Config | None = None
) -> Direction:
    target = pair.partner(source_language)
    return Direction(
        source_language=source_language,
        target_language=target,
        audio_track_name=track_name_for(target),
    )


def build_session(
    source_language: str,
    pair: LanguagePair = DEFAULT_PAIR,
    config: Config | None = None,
) -> tuple[AgentSession, TranslatorAgent]:
    """Create an AgentSession that hears ``source_language`` and speaks the partner."""
    direction = direction_for(source_language, pair)
    if config is None:  # pragma: no cover - callers always pass config
        raise ValueError("config is required")

    # the bundled silero VAD is a native model that cannot load without AVX2; when
    # it is unavailable, fall back to STT-based turn detection (see native_compat).
    native_vad = native_inference_available()

    session = AgentSession(
        stt=inference.STT(model=config.stt_model, language=direction.source_language),
        llm=inference.LLM(model=config.llm_model),
        tts=inference.TTS(
            model=config.tts_model,
            voice=config.voice_for(direction.target_language),
            language=direction.target_language,
        ),
        vad=NOT_GIVEN if native_vad else None,
        turn_detection=NOT_GIVEN if native_vad else "stt",
    )
    agent = TranslatorAgent(
        source_language=direction.source_language,
        target_language=direction.target_language,
    )
    return session, agent
