"""Environment parsing and validation for the interpreter agent.

This module intentionally has no LiveKit dependencies so it can be unit tested
without the agent runtime. Secret values are never included in error messages.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_STT_MODEL = "deepgram/nova-3"
DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
DEFAULT_TTS_VOICE_EN = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
DEFAULT_TTS_VOICE_BN = "f786b574-daa5-4673-aa0c-cbe3e8534c02"
DEFAULT_AGENT_NAME = "bengali-english-interpreter"
DEFAULT_TOKEN_TTL_SECONDS = 3600

_REQUIRED_VARS = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    stt_model: str = DEFAULT_STT_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    tts_voice_en: str = DEFAULT_TTS_VOICE_EN
    tts_voice_bn: str = DEFAULT_TTS_VOICE_BN
    bengali_language: str = "bn"
    english_language: str = "en"
    agent_name: str = DEFAULT_AGENT_NAME
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS

    def voice_for(self, language: str) -> str:
        if language == self.bengali_language:
            return self.tts_voice_bn
        if language == self.english_language:
            return self.tts_voice_en
        raise ConfigError(f"No TTS voice configured for language {language!r}")


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

    return Config(
        livekit_url=url,
        livekit_api_key=source["LIVEKIT_API_KEY"].strip(),
        livekit_api_secret=source["LIVEKIT_API_SECRET"].strip(),
        stt_model=(source.get("STT_MODEL") or "").strip() or DEFAULT_STT_MODEL,
        llm_model=(source.get("LLM_MODEL") or "").strip() or DEFAULT_LLM_MODEL,
        tts_model=(source.get("TTS_MODEL") or "").strip() or DEFAULT_TTS_MODEL,
        tts_voice_en=(source.get("TTS_VOICE_EN") or "").strip() or DEFAULT_TTS_VOICE_EN,
        tts_voice_bn=(source.get("TTS_VOICE_BN") or "").strip() or DEFAULT_TTS_VOICE_BN,
        bengali_language=(source.get("BENGALI_LANGUAGE") or "").strip() or "bn",
        english_language=(source.get("ENGLISH_LANGUAGE") or "").strip() or "en",
        agent_name=(source.get("AGENT_NAME") or "").strip() or DEFAULT_AGENT_NAME,
        token_ttl_seconds=ttl,
    )
