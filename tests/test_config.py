"""Configuration validation tests. Secret values must never surface in errors."""

from __future__ import annotations

import pytest

from agent.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE_JA,
    ConfigError,
    load_config,
)

SECRET = "super-secret-value-do-not-leak"
API_KEY = "APIkey123456abcdef"


def base_env(**overrides: str) -> dict[str, str]:
    env = {
        "LIVEKIT_URL": "wss://example.livekit.cloud",
        "LIVEKIT_API_KEY": API_KEY,
        "LIVEKIT_API_SECRET": SECRET,
    }
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


class TestRequiredSettings:
    @pytest.mark.parametrize("missing", ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"])
    def test_missing_required_var_fails_with_name_only(self, missing: str) -> None:
        env = {k: v for k, v in base_env().items() if k != missing}
        with pytest.raises(ConfigError) as exc:
            load_config(env)
        message = str(exc.value)
        assert missing in message
        # The values of the *other* settings (including secrets) must not leak.
        assert SECRET not in message
        assert API_KEY not in message

    def test_all_missing_reported_at_once(self) -> None:
        with pytest.raises(ConfigError) as exc:
            load_config({})
        message = str(exc.value)
        for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            assert name in message

    def test_whitespace_counts_as_missing(self) -> None:
        with pytest.raises(ConfigError):
            load_config(base_env(LIVEKIT_API_SECRET="   "))

    @pytest.mark.parametrize("url", ["not-a-url", "ftp://example", "example.livekit.cloud"])
    def test_invalid_url_rejected_without_secrets(self, url: str) -> None:
        with pytest.raises(ConfigError) as exc:
            load_config(base_env(LIVEKIT_URL=url))
        assert "LIVEKIT_URL" in str(exc.value)
        assert SECRET not in str(exc.value)


class TestValuesAndDefaults:
    def test_valid_env_parses(self) -> None:
        config = load_config(base_env())
        assert config.livekit_url == "wss://example.livekit.cloud"
        assert config.livekit_api_key == API_KEY
        assert config.livekit_api_secret == SECRET

    def test_model_defaults(self) -> None:
        config = load_config(base_env())
        assert config.stt_model == DEFAULT_STT_MODEL
        assert config.llm_model == DEFAULT_LLM_MODEL
        assert config.tts_model == DEFAULT_TTS_MODEL
        assert set(config.tts_voices) == {"bn", "en", "ja"}

    def test_voice_defaults_match_documented_cartesia_ids(self) -> None:
        config = load_config(base_env())
        # Cartesia rejects unknown voice IDs with "TTS provider completed without
        # producing audio", so these must match real Cartesia voices.
        # en/bn: LiveKit docs voice list; ja: Cartesia Japanese voice library
        # ("Yuzuki"), verified to synthesize ja via LiveKit Inference.
        assert config.voice_for("en") == "47c38ca4-5f35-497b-b1a3-415245fb35e1"
        assert config.voice_for("bn") == "314be1d2-3d14-468d-be40-08a1af7df49d"
        assert config.voice_for("ja") == DEFAULT_TTS_VOICE_JA
        assert DEFAULT_TTS_VOICE_JA == "aa3ccc4a-cfd8-405c-acf5-1873a527b006"
        # every supported language must resolve to a distinct, non-empty voice
        voices = {code: config.voice_for(code) for code in ("bn", "en", "ja")}
        assert all(voices.values())
        assert len(set(voices.values())) == 3

    def test_model_overrides(self) -> None:
        config = load_config(
            base_env(
                STT_MODEL="custom/stt",
                LLM_MODEL="custom/llm",
                TTS_MODEL="custom/tts",
                TTS_VOICE_BN="voice-bn",
                TTS_VOICE_EN="voice-en",
                TTS_VOICE_JA="voice-ja",
                AGENT_NAME="custom-agent",
            )
        )
        assert config.stt_model == "custom/stt"
        assert config.llm_model == "custom/llm"
        assert config.tts_model == "custom/tts"
        assert config.voice_for("bn") == "voice-bn"
        assert config.voice_for("en") == "voice-en"
        assert config.voice_for("ja") == "voice-ja"
        assert config.agent_name == "custom-agent"

    @pytest.mark.parametrize("bad_ttl", ["abc", "0", "-5"])
    def test_invalid_ttl_rejected(self, bad_ttl: str) -> None:
        with pytest.raises(ConfigError, match="TOKEN_TTL_SECONDS"):
            load_config(base_env(TOKEN_TTL_SECONDS=bad_ttl))

    def test_valid_ttl_parsed(self) -> None:
        assert load_config(base_env(TOKEN_TTL_SECONDS="120")).token_ttl_seconds == 120

    def test_unknown_voice_language_raises(self) -> None:
        config = load_config(base_env())
        with pytest.raises(ConfigError, match="No TTS voice"):
            config.voice_for("fr")

    def test_exception_text_never_contains_secret(self) -> None:
        try:
            load_config(base_env(TOKEN_TTL_SECONDS="nope"))
        except ConfigError as exc:
            text = str(exc)
            assert SECRET not in text
            assert API_KEY not in text
        else:  # pragma: no cover
            raise AssertionError("expected ConfigError")


class TestVoiceCloning:
    def test_disabled_by_default(self) -> None:
        config = load_config(base_env())
        assert config.voice_cloning_enabled is False
        assert config.cartesia_api_key == ""
        assert config.clone_sample_seconds == 15
        assert config.clone_timeout_seconds == 90

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_truthy_values_enable(self, value: str) -> None:
        config = load_config(
            base_env(VOICE_CLONING_ENABLED=value, CARTESIA_API_KEY="sk_cartesia")
        )
        assert config.voice_cloning_enabled is True
        assert config.cartesia_api_key == "sk_cartesia"

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
    def test_falsy_or_garbage_values_disabled(self, value: str) -> None:
        config = load_config(base_env(VOICE_CLONING_ENABLED=value))
        assert config.voice_cloning_enabled is False

    def test_enabled_without_api_key_is_config_error(self) -> None:
        with pytest.raises(ConfigError) as exc:
            load_config(base_env(VOICE_CLONING_ENABLED="true"))
        message = str(exc.value)
        assert "CARTESIA_API_KEY" in message
        assert "VOICE_CLONING_ENABLED" in message
        # must not leak any secrets
        assert SECRET not in message
        assert API_KEY not in message

    def test_clone_sample_seconds_bounded(self) -> None:
        assert (
            load_config(base_env(CLONE_SAMPLE_SECONDS="20")).clone_sample_seconds == 20
        )
        for bad in ("9", "31", "abc"):
            with pytest.raises(ConfigError, match="CLONE_SAMPLE_SECONDS"):
                load_config(base_env(CLONE_SAMPLE_SECONDS=bad))

    def test_clone_timeout_seconds_bounded(self) -> None:
        assert load_config(base_env(CLONE_TIMEOUT_SECONDS="120")).clone_timeout_seconds == 120
        for bad in ("0", "-1", "abc"):
            with pytest.raises(ConfigError, match="CLONE_TIMEOUT_SECONDS"):
                load_config(base_env(CLONE_TIMEOUT_SECONDS=bad))
