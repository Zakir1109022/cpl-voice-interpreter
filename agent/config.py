"""Environment parsing and validation for the interpreter agent.

This module intentionally has no LiveKit dependencies so it can be unit tested
without the agent runtime. Secret values are never included in error messages.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_STT_MODEL = "deepgram/nova-3"
DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
DEFAULT_TTS_VOICE_EN = "47c38ca4-5f35-497b-b1a3-415245fb35e1"
DEFAULT_TTS_VOICE_BN = "314be1d2-3d14-468d-be40-08a1af7df49d"
DEFAULT_TTS_VOICE_JA = "aa3ccc4a-cfd8-405c-acf5-1873a527b006"
DEFAULT_AGENT_NAME = "meeting-interpreter"
DEFAULT_TOKEN_TTL_SECONDS = 3600

# Dynamic voice preservation (per-participant voice cloning) defaults.
DEFAULT_CLONE_SAMPLE_SECONDS = 15
DEFAULT_CLONE_TIMEOUT_SECONDS = 90
MIN_CLONE_SAMPLE_SECONDS = 10
MAX_CLONE_SAMPLE_SECONDS = 30

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# language code -> env var name that overrides its TTS voice
_VOICE_VARS: Mapping[str, tuple[str, str]] = {
    "en": ("TTS_VOICE_EN", DEFAULT_TTS_VOICE_EN),
    "bn": ("TTS_VOICE_BN", DEFAULT_TTS_VOICE_BN),
    "ja": ("TTS_VOICE_JA", DEFAULT_TTS_VOICE_JA),
}

_REQUIRED_VARS = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _default_voices() -> dict[str, str]:
    return {language: default for language, (_, default) in _VOICE_VARS.items()}


@dataclass(frozen=True)
class Config:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    stt_model: str = DEFAULT_STT_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    tts_voices: Mapping[str, str] = field(default_factory=_default_voices)
    agent_name: str = DEFAULT_AGENT_NAME
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS
    voice_cloning_enabled: bool = False
    cartesia_api_key: str = ""
    clone_sample_seconds: int = DEFAULT_CLONE_SAMPLE_SECONDS
    clone_timeout_seconds: int = DEFAULT_CLONE_TIMEOUT_SECONDS

    def voice_for(self, language: str) -> str:
        try:
            return self.tts_voices[language]
        except KeyError:
            raise ConfigError(f"No TTS voice configured for language {language!r}") from None


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Load and validate configuration from the given environment mapping.

    Raises ConfigError listing the names (never the values) of missing or
    invalid variables.
    """
    source = os.environ if env is None else env

    missing = [name for name in _REQUIRED_VARS if not (source.get(name) or "").strip()]
    if missing:
        raise ConfigError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in your LiveKit Cloud credentials."
        )

    url = source["LIVEKIT_URL"].strip()
    if not url.startswith(("wss://", "ws://", "http://", "https://")):
        raise ConfigError("LIVEKIT_URL must be a ws://, wss://, http:// or https:// URL.")

    ttl_raw = (source.get("TOKEN_TTL_SECONDS") or "").strip()
    try:
        ttl = int(ttl_raw) if ttl_raw else DEFAULT_TOKEN_TTL_SECONDS
    except ValueError:
        raise ConfigError("TOKEN_TTL_SECONDS must be an integer number of seconds.") from None
    if ttl <= 0:
        raise ConfigError("TOKEN_TTL_SECONDS must be a positive integer.")

    voices = {
        language: (source.get(var) or "").strip() or default
        for language, (var, default) in _VOICE_VARS.items()
    }

    cloning_raw = (source.get("VOICE_CLONING_ENABLED") or "").strip().lower()
    cloning_enabled = cloning_raw in _TRUTHY
    cartesia_api_key = (source.get("CARTESIA_API_KEY") or "").strip()
    if cloning_enabled and not cartesia_api_key:
        raise ConfigError(
            "VOICE_CLONING_ENABLED is set but CARTESIA_API_KEY is missing. "
            "Get a key at play.cartesia.ai/keys or disable voice cloning."
        )

    clone_sample_seconds = _parse_bounded_int(
        source,
        "CLONE_SAMPLE_SECONDS",
        default=DEFAULT_CLONE_SAMPLE_SECONDS,
        low=MIN_CLONE_SAMPLE_SECONDS,
        high=MAX_CLONE_SAMPLE_SECONDS,
    )
    clone_timeout_seconds = _parse_bounded_int(
        source,
        "CLONE_TIMEOUT_SECONDS",
        default=DEFAULT_CLONE_TIMEOUT_SECONDS,
        low=1,
        high=3600,
    )

    return Config(
        livekit_url=url,
        livekit_api_key=source["LIVEKIT_API_KEY"].strip(),
        livekit_api_secret=source["LIVEKIT_API_SECRET"].strip(),
        stt_model=(source.get("STT_MODEL") or "").strip() or DEFAULT_STT_MODEL,
        llm_model=(source.get("LLM_MODEL") or "").strip() or DEFAULT_LLM_MODEL,
        tts_model=(source.get("TTS_MODEL") or "").strip() or DEFAULT_TTS_MODEL,
        tts_voices=voices,
        agent_name=(source.get("AGENT_NAME") or "").strip() or DEFAULT_AGENT_NAME,
        token_ttl_seconds=ttl,
        voice_cloning_enabled=cloning_enabled,
        cartesia_api_key=cartesia_api_key,
        clone_sample_seconds=clone_sample_seconds,
        clone_timeout_seconds=clone_timeout_seconds,
    )


def _parse_bounded_int(
    source: Mapping[str, str],
    name: str,
    *,
    default: int,
    low: int,
    high: int,
) -> int:
    """Parse an optional integer env var, enforcing an inclusive range."""
    raw = (source.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer number of seconds.") from None
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}.")
    return value
