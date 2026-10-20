"""Voice enrollment tests: sample buffering, WAV encoding, and the clone client.

The Cartesia API is exercised through ``httpx2.MockTransport``; no network and
no real API key are involved.
"""

from __future__ import annotations

import httpx2 as httpx
import numpy as np
import pytest
from livekit import rtc

from agent.voice_enroll import (
    ABSOLUTE_MIN_SAMPLE_SECONDS,
    CONSENT_ATTRIBUTE,
    ClonedVoice,
    EnrollmentBuffer,
    VoiceEnroller,
    encode_wav,
    frame_rms,
    has_voice_consent,
    voice_name_for,
)

SAMPLE_RATE = 16000


def speech_frame(*, seconds: float = 0.02, amplitude: int = 8000) -> rtc.AudioFrame:
    samples = int(SAMPLE_RATE * seconds)
    data = np.full(samples, amplitude, dtype=np.int16).tobytes()
    return rtc.AudioFrame(data, SAMPLE_RATE, 1, samples)


def silence_frame(*, seconds: float = 0.02) -> rtc.AudioFrame:
    samples = int(SAMPLE_RATE * seconds)
    data = np.zeros(samples, dtype=np.int16).tobytes()
    return rtc.AudioFrame(data, SAMPLE_RATE, 1, samples)


class TestConsent:
    def test_granted(self) -> None:
        assert has_voice_consent({CONSENT_ATTRIBUTE: "true"})
        assert has_voice_consent({CONSENT_ATTRIBUTE: " TRUE "})

    @pytest.mark.parametrize(
        "attributes",
        [{}, None, {CONSENT_ATTRIBUTE: "false"}, {CONSENT_ATTRIBUTE: ""}, {"language": "bn"}],
    )
    def test_not_granted(self, attributes: dict[str, str] | None) -> None:
        assert not has_voice_consent(attributes)


class TestWavEncoding:
    def test_header_fields(self) -> None:
        pcm = b"\x01\x00" * 1600
        wav = encode_wav(pcm, SAMPLE_RATE)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert int.from_bytes(wav[24:28], "little") == SAMPLE_RATE  # sample rate
        assert int.from_bytes(wav[22:24], "little") == 1  # mono
        assert int.from_bytes(wav[34:36], "little") == 16  # bit depth
        assert int.from_bytes(wav[40:44], "little") == len(pcm)  # data size
        assert int.from_bytes(wav[4:8], "little") == len(wav) - 8  # riff size
        assert wav[44:] == pcm

    def test_frame_rms_distinguishes_speech_from_silence(self) -> None:
        assert frame_rms(speech_frame()) > 1000
        assert frame_rms(silence_frame()) == 0.0


class TestEnrollmentBuffer:
    def test_collects_to_target_and_encodes(self) -> None:
        buffer = EnrollmentBuffer(target_seconds=0.5, min_seconds=0.2, max_seconds=1.0)
        complete = False
        for _ in range(50):  # 50 * 20ms = 1s of available speech
            complete = buffer.add_frame(speech_frame())
            if complete:
                break
        assert complete
        assert buffer.is_complete
        assert buffer.seconds_collected >= 0.5

        wav = buffer.wav_bytes()
        assert wav is not None
        assert wav[:4] == b"RIFF"
        data_size = int.from_bytes(wav[40:44], "little")
        assert data_size == int(SAMPLE_RATE * 2 * buffer.seconds_collected)

    def test_silence_is_skipped(self) -> None:
        buffer = EnrollmentBuffer(target_seconds=0.4, min_seconds=0.1, max_seconds=1.0)
        for _ in range(100):
            assert not buffer.add_frame(silence_frame())
        assert buffer.seconds_collected == 0.0
        assert buffer.wav_bytes() is None

    def test_below_minimum_returns_none(self) -> None:
        buffer = EnrollmentBuffer(target_seconds=1.0, min_seconds=0.5, max_seconds=2.0)
        for _ in range(10):  # only 0.2s of speech: > 0 but < min_seconds
            buffer.add_frame(speech_frame())
        assert not buffer.is_complete
        assert buffer.wav_bytes() is None

    def test_hard_cap_stops_at_max_seconds(self) -> None:
        buffer = EnrollmentBuffer(target_seconds=0.6, min_seconds=0.1, max_seconds=0.5)
        for _ in range(100):
            buffer.add_frame(speech_frame())
        assert buffer.seconds_collected <= 0.5 + 1e-9
        assert buffer.is_complete

    def test_defaults_respect_absolute_minimum(self) -> None:
        buffer = EnrollmentBuffer()
        assert buffer._min_seconds == ABSOLUTE_MIN_SAMPLE_SECONDS

    def test_invalid_bounds_rejected(self) -> None:
        with pytest.raises(ValueError):
            EnrollmentBuffer(min_seconds=5.0, max_seconds=1.0)


class TestVoiceName:
    def test_sanitizes_identity(self) -> None:
        assert voice_name_for("alice-1") == "interpreter-alice-1"
        assert voice_name_for("../../etc/passwd").startswith("interpreter-")
        assert len(voice_name_for("x" * 200)) <= 60
        assert voice_name_for("!!") == "interpreter-participant"


def clone_handler(calls: list[dict[str, object]]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            request.read()
            calls.append(
                {
                    "url": str(request.url),
                    "api_key": request.headers.get("X-API-Key"),
                    "version": request.headers.get("Cartesia-Version"),
                    "body": request.content,
                }
            )
            return httpx.Response(200, json={"id": "v_clone_123"})
        if request.method == "DELETE":
            calls.append({"delete_url": str(request.url)})
            return httpx.Response(204)
        return httpx.Response(500)

    return httpx.MockTransport(handle)


class TestVoiceEnroller:
    async def test_enroll_success_and_cache(self) -> None:
        calls: list[dict[str, object]] = []
        client = httpx.AsyncClient(transport=clone_handler(calls))
        enroller = VoiceEnroller(api_key="sk_test", client=client)

        voice = await enroller.enroll("alice", language="bn", wav=b"RIFF....")
        assert isinstance(voice, ClonedVoice)
        assert voice.voice_id == "v_clone_123"
        assert voice.identity == "alice"
        assert voice.language == "bn"

        # Second call is served from cache: no extra HTTP round trip.
        again = await enroller.enroll("alice", language="bn", wav=b"RIFF....")
        assert again is voice
        assert len(calls) == 1

        call = calls[0]
        assert call["url"] == "https://api.cartesia.ai/voices/clone"
        assert call["api_key"] == "sk_test"
        assert call["version"] is not None
        body = call["body"]
        assert isinstance(body, bytes) and b"alice" in body  # multipart contains name

        await enroller.aclose()
        await client.aclose()

    async def test_http_error_returns_none(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="bad clip")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        assert await enroller.enroll("bob", language="ja", wav=b"x") is None
        assert enroller.get("bob") is None
        await client.aclose()

    async def test_invalid_json_returns_none(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="not-json")
            )
        )
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        assert await enroller.enroll("carol", language="en", wav=b"x") is None
        await client.aclose()

    async def test_missing_id_returns_none(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={})
            )
        )
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        assert await enroller.enroll("dave", language="en", wav=b"x") is None
        await client.aclose()

    async def test_forget_deletes_remote_voice(self) -> None:
        calls: list[dict[str, object]] = []
        client = httpx.AsyncClient(transport=clone_handler(calls))
        enroller = VoiceEnroller(api_key="sk_test", client=client)

        voice = await enroller.enroll("erin", language="bn", wav=b"x")
        assert voice is not None
        await enroller.forget("erin")
        assert enroller.get("erin") is None
        assert any("delete_url" in call for call in calls)
        # Forgetting an unknown identity is a no-op.
        await enroller.forget("nobody")
        await client.aclose()

    async def test_aclose_removes_all_voices(self) -> None:
        calls: list[dict[str, object]] = []
        client = httpx.AsyncClient(transport=clone_handler(calls))
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        await enroller.enroll("frank", language="bn", wav=b"x")
        await enroller.enroll("grace", language="ja", wav=b"x")
        await enroller.aclose()
        deletes = [c for c in calls if "delete_url" in c]
        assert len(deletes) == 2
        assert enroller.cached_voices == {}
        await client.aclose()

    async def test_network_error_returns_none(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        assert await enroller.enroll("heidi", language="bn", wav=b"x") is None
        await client.aclose()

    def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError):
            VoiceEnroller(api_key="")

    async def test_request_contains_multipart_clip(self) -> None:
        captured: dict[str, bytes] = {}

        def handle(request: httpx.Request) -> httpx.Response:
            request.read()
            captured["body"] = request.content
            captured["content_type"] = request.headers.get(
                "content-type", ""
            ).encode()
            return httpx.Response(200, json={"id": "v_x"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        enroller = VoiceEnroller(api_key="sk_test", client=client)
        await enroller.enroll("ivan", language="bn", wav=b"RIFFdata")
        body = captured["body"]
        assert b'filename="sample.wav"' in body
        assert b"RIFFdata" in body
        assert b"multipart/form-data" in captured["content_type"]
        await client.aclose()
