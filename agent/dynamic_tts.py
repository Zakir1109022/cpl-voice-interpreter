"""A TTS that can switch voices mid-session.

Built for dynamic voice preservation: the interpreter session starts on the
configured fallback voice and, once a participant's clone is ready, swaps to a
Cartesia TTS speaking with that clone. The framework holds one TTS instance per
session (``AgentSession.tts`` is read-only), so the swap happens *inside* this
wrapper: every call is delegated to whichever inner TTS is current.

Event forwarding matters here — the agent activity subscribes to
``metrics_collected``/``error`` on the wrapper once, so inner emissions are
re-emitted on the wrapper for whichever inner TTS produced them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

from .config import Config

logger = logging.getLogger("interpreter")


def cartesia_voice_factory(config: Config, language: str) -> Callable[[str], tts.TTS]:
    """Build a factory that synthesizes with a cloned Cartesia voice id.

    Custom clones are not routable through LiveKit Inference, so this uses the
    Cartesia plugin with the project's own Cartesia API key.
    """

    def create(voice_id: str) -> tts.TTS:
        from livekit.plugins import cartesia  # guarded: only needed when cloning runs

        model = config.tts_model.split("/", 1)[-1]
        return cartesia.TTS(
            model=model,
            voice=voice_id,
            language=language,
            api_key=config.cartesia_api_key,
        )

    return create


class DynamicVoiceTTS(tts.TTS):
    """Delegates to a current inner TTS; swaps it when a cloned voice arrives."""

    def __init__(
        self,
        fallback: tts.TTS,
        *,
        voice_factory: Callable[[str], tts.TTS],
    ) -> None:
        super().__init__(
            capabilities=fallback.capabilities,
            sample_rate=fallback.sample_rate,
            num_channels=fallback.num_channels,
        )
        self._voice_factory = voice_factory
        self._current: tts.TTS = fallback
        self._retired: list[tts.TTS] = []
        self._forwarding: list[tuple[tts.TTS, str, Callable[..., None]]] = []
        self._attach(self._current)

    # ------------------------------------------------------------- inner wiring

    def _attach(self, inner: tts.TTS) -> None:
        for event in ("metrics_collected", "error"):
            handler = self._make_forwarder(event)
            inner.on(event, handler)  # type: ignore[arg-type]
            self._forwarding.append((inner, event, handler))

    def _detach(self, inner: tts.TTS) -> None:
        remaining: list[tuple[tts.TTS, str, Callable[..., None]]] = []
        for stored, event, handler in self._forwarding:
            if stored is inner:
                inner.off(event, handler)  # type: ignore[arg-type]
            else:
                remaining.append((stored, event, handler))
        self._forwarding = remaining

    def _make_forwarder(self, event: str) -> Callable[..., None]:
        def forward(*args: object, **kwargs: object) -> None:
            self.emit(event, *args, **kwargs)  # type: ignore[arg-type]

        return forward

    @property
    def current_tts(self) -> tts.TTS:
        return self._current

    def set_cloned_voice(self, voice_id: str) -> bool:
        """Switch to a Cartesia TTS using ``voice_id``. Never raises.

        On any failure the fallback voice stays in place so translation continues.
        """
        try:
            inner = self._voice_factory(voice_id)
        except Exception as exc:  # noqa: BLE001 - a missing plugin/key must not break audio
            logger.warning("could not build cloned-voice TTS; keeping fallback: %s", exc)
            return False
        previous = self._current
        self._detach(previous)
        self._retired.append(previous)
        self._current = inner
        self._attach(inner)
        inner._set_expressive(self._expressive)
        inner.prewarm()
        logger.info("TTS swapped to cloned voice %s", voice_id)
        return True

    # ------------------------------------------------------------- delegation

    @property
    def capabilities(self) -> tts.TTSCapabilities:
        return self._current.capabilities

    @property
    def sample_rate(self) -> int:
        return self._current.sample_rate

    @property
    def num_channels(self) -> int:
        return self._current.num_channels

    @property
    def model(self) -> str:
        return self._current.model

    @property
    def provider(self) -> str:
        return self._current.provider

    @property
    def label(self) -> str:
        return self._current.label

    @property
    def metrics_metadata(self) -> dict[str, str]:
        return self._current.metrics_metadata

    @property
    def markup(self) -> tts.TTS.Markup:
        return self._current.markup

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        inner = self._current  # snapshot so one synthesis never mixes voices
        return inner.synthesize(text, conn_options=conn_options)

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.SynthesizeStream:
        return self._current.stream(conn_options=conn_options)

    def prewarm(self) -> None:
        self._current.prewarm()

    def _set_expressive(self, enabled: bool) -> None:
        super()._set_expressive(enabled)
        self._current._set_expressive(enabled)

    async def aclose(self) -> None:
        for inner in [self._current, *self._retired]:
            try:
                await inner.aclose()
            except Exception:  # noqa: BLE001 - teardown must not raise
                logger.warning("closing an inner TTS failed", exc_info=True)
        self._retired.clear()


__all__ = ["DynamicVoiceTTS", "cartesia_voice_factory"]
