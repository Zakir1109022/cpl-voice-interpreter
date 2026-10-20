"""DynamicVoiceTTS tests: fallback delegation, voice swap, and event forwarding.

Uses lightweight fake TTS instances so no network, plugin, or API key is needed.
"""

from __future__ import annotations

from typing import Any, cast

from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

from agent.dynamic_tts import DynamicVoiceTTS, cartesia_voice_factory


class FakeInnerTTS(tts.TTS):
    """Minimal concrete TTS that records calls instead of synthesizing audio."""

    def __init__(self, name: str = "fallback", *, sample_rate: int = 24000) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self.name = name
        self.synthesized: list[str] = []
        self.stream_calls = 0
        self.prewarm_calls = 0
        self.closed = False

    @property
    def model(self) -> str:
        return f"fake/{self.name}"

    @property
    def provider(self) -> str:
        return "fake"

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        self.synthesized.append(text)
        return cast(tts.ChunkedStream, f"chunked:{self.name}:{text}")

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.SynthesizeStream:
        self.stream_calls += 1
        return cast(tts.SynthesizeStream, f"stream:{self.name}")

    def prewarm(self) -> None:
        self.prewarm_calls += 1

    async def aclose(self) -> None:
        self.closed = True


def make_wrapper(
    names: list[str] | None = None,
    *,
    factory_error: Exception | None = None,
) -> tuple[DynamicVoiceTTS, FakeInnerTTS, dict[str, FakeInnerTTS]]:
    fallback = FakeInnerTTS("fallback")
    built: dict[str, FakeInnerTTS] = {}

    def factory(voice_id: str) -> tts.TTS:
        if factory_error is not None:
            raise factory_error
        inner = FakeInnerTTS(voice_id)
        built[voice_id] = inner
        return inner

    wrapper = DynamicVoiceTTS(fallback, voice_factory=factory)
    return wrapper, fallback, built


class TestFallbackDelegation:
    def test_starts_on_fallback(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        assert wrapper.current_tts is fallback

    def test_delegates_synthesize(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        result = wrapper.synthesize("hello")
        assert result == "chunked:fallback:hello"
        assert fallback.synthesized == ["hello"]

    def test_delegates_stream(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        assert wrapper.stream() == "stream:fallback"
        assert fallback.stream_calls == 1

    def test_delegates_properties(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        assert wrapper.capabilities == fallback.capabilities
        assert wrapper.sample_rate == fallback.sample_rate
        assert wrapper.num_channels == fallback.num_channels
        assert wrapper.model == "fake/fallback"
        assert wrapper.provider == "fake"

    def test_prewarm_reaches_inner(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        wrapper.prewarm()
        assert fallback.prewarm_calls == 1

    def test_expressive_propagates_to_inner(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        wrapper._set_expressive(True)
        assert fallback._expressive is True


class TestVoiceSwap:
    def test_set_cloned_voice_swaps_inner(self) -> None:
        wrapper, fallback, built = make_wrapper()
        assert wrapper.set_cloned_voice("v_clone") is True
        assert wrapper.current_tts is built["v_clone"]
        assert wrapper.current_tts is not fallback

        # New synthesis goes to the cloned voice; the fallback is untouched.
        assert wrapper.synthesize("hi") == "chunked:v_clone:hi"
        assert built["v_clone"].synthesized == ["hi"]
        assert fallback.synthesized == []

    def test_factory_failure_keeps_fallback(self) -> None:
        wrapper, fallback, _ = make_wrapper(factory_error=RuntimeError("no plugin"))
        assert wrapper.set_cloned_voice("v_clone") is False
        assert wrapper.current_tts is fallback
        assert wrapper.synthesize("still works") == "chunked:fallback:still works"

    def test_clone_gets_prewarmed(self) -> None:
        wrapper, _, built = make_wrapper()
        wrapper.set_cloned_voice("v_clone")
        assert built["v_clone"].prewarm_calls == 1

    def test_expressive_carried_to_cloned_voice(self) -> None:
        wrapper, _, built = make_wrapper()
        wrapper._set_expressive(True)
        wrapper.set_cloned_voice("v_clone")
        assert built["v_clone"]._expressive is True

    def test_concurrent_synthesis_not_mixed_after_swap(self) -> None:
        # A synthesis started before the swap must finish on the old voice.
        wrapper, fallback, built = make_wrapper()
        pending = wrapper.synthesize("first")
        wrapper.set_cloned_voice("v_clone")
        assert pending == "chunked:fallback:first"
        assert wrapper.synthesize("second") == "chunked:v_clone:second"
        assert fallback.synthesized == ["first"]
        assert built["v_clone"].synthesized == ["second"]

    async def test_aclose_closes_current_and_retired(self) -> None:
        wrapper, fallback, built = make_wrapper()
        wrapper.set_cloned_voice("v_clone")
        await wrapper.aclose()
        assert fallback.closed
        assert built["v_clone"].closed


class TestEventForwarding:
    def test_inner_events_re_emitted_on_wrapper(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        metrics: list[Any] = []
        errors: list[Any] = []
        wrapper.on("metrics_collected", metrics.append)  # type: ignore[arg-type]
        wrapper.on("error", errors.append)  # type: ignore[arg-type]

        metric_payload = object()
        error_payload = object()
        fallback.emit("metrics_collected", metric_payload)
        fallback.emit("error", error_payload)
        assert metrics == [metric_payload]
        assert errors == [error_payload]

    def test_cloned_voice_events_forwarded_after_swap(self) -> None:
        wrapper, _, built = make_wrapper()
        metrics: list[Any] = []
        wrapper.on("metrics_collected", metrics.append)  # type: ignore[arg-type]

        wrapper.set_cloned_voice("v_clone")
        payload = object()
        built["v_clone"].emit("metrics_collected", payload)
        assert metrics == [payload]

    def test_detached_voice_no_longer_forwards(self) -> None:
        wrapper, fallback, _ = make_wrapper()
        metrics: list[Any] = []
        wrapper.on("metrics_collected", metrics.append)  # type: ignore[arg-type]

        wrapper.set_cloned_voice("v_clone")
        fallback.emit("metrics_collected", object())
        assert metrics == []


class TestCartesiaVoiceFactory:
    def test_factory_builds_plugin_tts(self) -> None:
        from agent.config import Config

        config = Config(
            livekit_url="wss://example.livekit.cloud",
            livekit_api_key="lk_key",
            livekit_api_secret="lk_secret",
            voice_cloning_enabled=True,
            cartesia_api_key="sk_test",
        )
        create = cartesia_voice_factory(config, "bn")
        inner = create("v_clone_abc")
        from livekit.plugins import cartesia

        assert isinstance(inner, cartesia.TTS)
        assert inner._opts.api_key == "sk_test"
        assert inner._opts.language is not None
        assert inner._opts.language.language == "bn"
        assert inner._opts.voice == "v_clone_abc"

    def test_factory_strips_provider_prefix_from_model(self) -> None:
        from agent.config import Config

        config = Config(
            livekit_url="wss://example.livekit.cloud",
            livekit_api_key="lk_key",
            livekit_api_secret="lk_secret",
            tts_model="cartesia/sonic-3",
            cartesia_api_key="sk_test",
        )
        inner = cartesia_voice_factory(config, "ja")("v_1")
        # LiveKit Inference model ids are "provider/model"; the plugin wants the
        # bare model name.
        assert inner.model == "sonic-3"
