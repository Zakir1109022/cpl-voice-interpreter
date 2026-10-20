"""Automatic voice enrollment for dynamic voice preservation.

Buffers the first clear seconds of a participant's speech from their audio track,
then creates a Cartesia instant voice clone so their translations are synthesized
in a voice that sounds like them. Nothing here talks to LiveKit rooms directly;
``agent/session.py`` owns the audio tap and calls into this module.

Privacy contract:
- Raw audio only ever lives in ``EnrollmentBuffer`` (memory, cleared once the
  sample is encoded); it is sent only to the Cartesia clone API, and only for
  participants who granted consent (``voice_cloning_consent`` attribute).
- The resulting remote voice clone is deleted when the participant leaves or the
  agent shuts down (``VoiceEnroller.forget``/``aclose``).
- Every API failure degrades to ``None`` so the caller keeps the fallback voice;
  enrollment never blocks translation.
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
import time

import httpx2 as httpx
import numpy as np
from livekit import rtc

logger = logging.getLogger("interpreter")

CLONE_URL = "https://api.cartesia.ai/voices/clone"
VOICE_URL_TEMPLATE = "https://api.cartesia.ai/voices/{voice_id}"
CLONE_API_VERSION = "2026-08-14"

# Participant attribute set by the web token endpoint when the user ticks the
# consent checkbox on the join screen.
CONSENT_ATTRIBUTE = "voice_cloning_consent"
CONSENT_GRANTED = "true"

# Enrollment audio is captured as 16 kHz mono PCM (AudioStream resamples).
ENROLL_SAMPLE_RATE = 16000

# Frames quieter than this RMS (0..32767) are treated as silence/background and
# skipped so the clone gets speech, not room tone.
MIN_FRAME_RMS = 500.0

# Cartesia recommends ~10 s of audio; below this we do not bother cloning.
ABSOLUTE_MIN_SAMPLE_SECONDS = 10.0
HARD_CAP_SAMPLE_SECONDS = 30.0

_VOICE_NAME_SANITIZE = re.compile(r"[^A-Za-z0-9._@-]+")


def has_voice_consent(attributes: dict[str, str] | None) -> bool:
    """True when the participant explicitly consented to voice cloning."""
    if not attributes:
        return False
    return attributes.get(CONSENT_ATTRIBUTE, "").strip().lower() == CONSENT_GRANTED


def frame_rms(frame: rtc.AudioFrame) -> float:
    """Root-mean-square amplitude of a 16-bit PCM frame."""
    samples = np.frombuffer(frame.data, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def encode_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw s16le mono PCM in a minimal RIFF/WAVE container."""
    byte_rate = sample_rate * 2
    block_align = 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        byte_rate,
        block_align,
        16,  # bits per sample
        b"data",
        len(pcm),
    )
    return header + pcm


class EnrollmentBuffer:
    """Accumulates speech frames until a usable enrollment sample is collected."""

    def __init__(
        self,
        *,
        target_seconds: float = 15.0,
        max_seconds: float = HARD_CAP_SAMPLE_SECONDS,
        min_seconds: float = ABSOLUTE_MIN_SAMPLE_SECONDS,
        sample_rate: int = ENROLL_SAMPLE_RATE,
    ) -> None:
        if min_seconds <= 0 or min_seconds > max_seconds:
            raise ValueError("min_seconds must be in (0, max_seconds]")
        if target_seconds > max_seconds:
            target_seconds = max_seconds
        self._target_seconds = target_seconds
        self._max_seconds = max_seconds
        self._min_seconds = min_seconds
        self._sample_rate = sample_rate
        self._chunks: list[bytes] = []
        self._collected_seconds = 0.0

    @property
    def seconds_collected(self) -> float:
        return self._collected_seconds

    @property
    def is_complete(self) -> bool:
        return self._collected_seconds >= self._target_seconds

    def add_frame(self, frame: rtc.AudioFrame) -> bool:
        """Add one frame; returns True once the target amount of speech is held."""
        if self.is_complete:
            return True
        if frame_rms(frame) < MIN_FRAME_RMS:
            return False
        # Enforce the hard cap by trim-if-over rather than refusing the frame.
        remaining = self._max_seconds - self._collected_seconds
        if remaining <= 0:
            return True
        chunk = bytes(frame.data)
        frame_seconds = frame.samples_per_channel / frame.sample_rate
        if frame_seconds > remaining:
            keep = int(len(chunk) * remaining / frame_seconds)
            keep -= keep % 2  # keep 16-bit sample alignment
            chunk = chunk[:keep]
            frame_seconds = remaining
        self._chunks.append(chunk)
        self._collected_seconds += frame_seconds
        return self.is_complete

    def wav_bytes(self) -> bytes | None:
        """Encoded sample, or None when less than the minimum speech was captured."""
        if self._collected_seconds < self._min_seconds:
            return None
        return encode_wav(b"".join(self._chunks), self._sample_rate)


class ClonedVoice:
    """A Cartesia voice cloned for one participant."""

    __slots__ = ("identity", "voice_id", "language")

    def __init__(self, identity: str, voice_id: str, language: str) -> None:
        self.identity = identity
        self.voice_id = voice_id
        self.language = language


def voice_name_for(identity: str) -> str:
    """A short, API-safe display name for a participant's cloned voice."""
    sanitized = _VOICE_NAME_SANITIZE.sub("-", identity).strip("-.") or "participant"
    return f"interpreter-{sanitized}"[:60]


class VoiceEnroller:
    """Creates and caches Cartesia instant clones per participant identity.

    All methods are failure-tolerant: cloning problems are logged and reported as
    ``None``/no-op so the translation pipeline keeps its fallback voice.
    """

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": CLONE_API_VERSION,
        }
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._voices: dict[str, ClonedVoice] = {}

    @property
    def cached_voices(self) -> dict[str, ClonedVoice]:
        return dict(self._voices)

    def get(self, identity: str) -> ClonedVoice | None:
        return self._voices.get(identity)

    async def enroll(
        self, identity: str, *, language: str, wav: bytes
    ) -> ClonedVoice | None:
        """Clone ``wav`` for ``identity``; returns the cached clone when present."""
        cached = self._voices.get(identity)
        if cached is not None:
            return cached

        try:
            response = await self._client.post(
                CLONE_URL,
                headers=self._headers,
                data={"name": voice_name_for(identity), "language": language},
                files={"clip": ("sample.wav", wav, "audio/wav")},
            )
        except httpx.HTTPError as exc:
            logger.warning("voice clone request for %s failed: %s", identity, exc)
            return None

        if response.status_code not in (200, 201):
            logger.warning(
                "voice clone for %s rejected with HTTP %s: %s",
                identity,
                response.status_code,
                response.text[:200],
            )
            return None

        try:
            voice_id = str(response.json().get("id") or "")
        except ValueError:
            voice_id = ""
        if not voice_id:
            logger.warning("voice clone for %s returned no voice id", identity)
            return None

        voice = ClonedVoice(identity=identity, voice_id=voice_id, language=language)
        self._voices[identity] = voice
        logger.info("voice clone ready for %s (voice_id=%s)", identity, voice_id)
        return voice

    async def forget(self, identity: str) -> None:
        """Drop the cached clone and delete it from Cartesia (privacy cleanup)."""
        voice = self._voices.pop(identity, None)
        if voice is None:
            return
        try:
            response = await self._client.delete(
                VOICE_URL_TEMPLATE.format(voice_id=voice.voice_id),
                headers=self._headers,
            )
            if response.status_code not in (200, 204, 404):
                logger.warning(
                    "could not delete voice clone for %s (HTTP %s)",
                    identity,
                    response.status_code,
                )
        except httpx.HTTPError as exc:
            logger.warning("could not delete voice clone for %s: %s", identity, exc)

    async def aclose(self) -> None:
        """Delete every clone we created, then release the HTTP client."""
        for identity in list(self._voices):
            await self.forget(identity)
        if self._owns_client:
            await self._client.aclose()


async def collect_enrollment_sample(
    track: rtc.Track,
    *,
    target_seconds: float,
    deadline_seconds: float,
) -> bytes | None:
    """Read ``track`` until the buffer fills or the deadline passes.

    Returns the encoded WAV sample, or ``None`` when too little speech arrived.
    The caller owns track subscription; this only consumes frames.
    """
    buffer = EnrollmentBuffer(target_seconds=target_seconds)
    deadline = time.monotonic() + deadline_seconds
    stream = rtc.AudioStream(
        track, sample_rate=ENROLL_SAMPLE_RATE, num_channels=1
    )
    try:
        async for event in stream:
            if buffer.add_frame(event.frame):
                break
            if time.monotonic() >= deadline:
                break
    finally:
        await stream.aclose()
    if not buffer.is_complete:
        logger.info(
            "enrollment sample for this speaker reached the deadline with %.1fs of speech",
            buffer.seconds_collected,
        )
    return buffer.wav_bytes()


async def wait_for_audio_track(
    participant: rtc.RemoteParticipant,
    *,
    timeout_seconds: float,
) -> rtc.Track | None:
    """Wait until the participant's microphone track is subscribed."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for publication in participant.track_publications.values():
            if (
                publication.kind == rtc.TrackKind.KIND_AUDIO
                and publication.track is not None
            ):
                return publication.track
        await asyncio.sleep(0.25)
    return None


__all__ = [
    "ABSOLUTE_MIN_SAMPLE_SECONDS",
    "CLONE_API_VERSION",
    "CONSENT_ATTRIBUTE",
    "CONSENT_GRANTED",
    "ENROLL_SAMPLE_RATE",
    "ClonedVoice",
    "EnrollmentBuffer",
    "VoiceEnroller",
    "collect_enrollment_sample",
    "encode_wav",
    "frame_rms",
    "has_voice_consent",
    "voice_name_for",
    "wait_for_audio_track",
]
