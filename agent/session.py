"""Room/session lifecycle: one translation session per source participant.

Routing invariants enforced here:
- A session only ever hears its linked source participant (RoomIO filter).
- Each session publishes speech translated into the *target* language under the
  track name ``translated-<lang>``.
- The agent's translated tracks are restricted, at the SFU level, to
  participants whose selected language is the target language.
"""

from __future__ import annotations

import asyncio
import json
import logging

from livekit import rtc
from livekit.agents import JobContext, room_io, utils

from .config import Config
from .dynamic_tts import DynamicVoiceTTS
from .routing import (
    DEFAULT_PAIR,
    LanguagePair,
    UnsupportedLanguageError,
    target_language_from_track_name,
    track_name_for,
    validate_language,
)
from .translation import build_session
from .voice_enroll import (
    VoiceEnroller,
    collect_enrollment_sample,
    has_voice_consent,
    wait_for_audio_track,
)

logger = logging.getLogger("interpreter")

STATUS_TOPIC = "interpreter-status"
_MAX_STATUS_MESSAGE = 400

# How long to wait for the participant's microphone track to subscribe before
# giving up on capturing a voice sample.
TRACK_WAIT_SECONDS = 30.0


def safe_error_message(exc: object, secret_values: tuple[str, ...] = ()) -> str:
    """Render an error for the frontend without leaking credentials."""
    text = f"{type(exc).__name__}: {exc}"
    for secret in secret_values:
        if secret and secret in text:
            text = text.replace(secret, "***")
    lowered = text.lower()
    for marker in ("api_key", "api_secret", "api secret", "authorization", "password", "token="):
        if marker in lowered:
            return f"{type(exc).__name__}: (error details redacted)"
    return text[:_MAX_STATUS_MESSAGE]


class InterpreterManager:
    """Owns per-participant translation sessions for one room."""

    def __init__(self, ctx: JobContext, config: Config, pair: LanguagePair = DEFAULT_PAIR) -> None:
        self._ctx = ctx
        self._config = config
        self._pair = pair
        self._sessions: dict[str, object] = {}
        self._tasks: set[asyncio.Task[object]] = set()
        self._translated_tracks: dict[str, str] = {}  # track sid -> target language
        self._closed = False
        # Dynamic voice preservation: one enroller per room, clones cached by
        # participant identity until they leave (then deleted for privacy).
        self._enroller: VoiceEnroller | None = None
        if config.voice_cloning_enabled and config.cartesia_api_key:
            self._enroller = VoiceEnroller(api_key=config.cartesia_api_key)
        self._enroll_tasks: dict[str, asyncio.Task[None]] = {}

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        room = self._ctx.room
        room.on("participant_connected", self.on_participant_connected)
        room.on("participant_disconnected", self.on_participant_disconnected)
        room.on("participant_attributes_changed", self.on_attributes_changed)
        room.on("local_track_published", self.on_local_track_published)
        room.on("local_track_unpublished", self.on_local_track_unpublished)

    async def aclose(self) -> None:
        self._closed = True
        room = self._ctx.room
        room.off("participant_connected", self.on_participant_connected)
        room.off("participant_disconnected", self.on_participant_disconnected)
        room.off("participant_attributes_changed", self.on_attributes_changed)
        room.off("local_track_published", self.on_local_track_published)
        room.off("local_track_unpublished", self.on_local_track_unpublished)

        await utils.aio.cancel_and_wait(*self._tasks)
        self._tasks.clear()

        sessions = list(self._sessions.values())
        self._sessions.clear()
        for session in sessions:
            await self._close_session(session, drain=True)

        if self._enroller is not None:
            # Privacy: every voice clone created for this room is deleted.
            try:
                await self._enroller.aclose()
            except Exception:  # noqa: BLE001 - teardown must not raise
                logger.warning("voice enroller cleanup failed", exc_info=True)

    # ------------------------------------------------------------------ events

    def on_participant_connected(self, participant: rtc.Participant) -> None:
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            return
        if participant.attributes.get("lk.publish_on_behalf"):
            return
        self._spawn(self._ensure_session(participant.identity))

    def on_participant_disconnected(self, participant: rtc.Participant) -> None:
        self._cancel_enrollment(participant.identity)
        session = self._sessions.pop(participant.identity, None)
        if session is not None:
            logger.info(
                "closing translation session for departed participant %s",
                participant.identity,
            )
            self._spawn(self._close_session(session, drain=False))
        if self._enroller is not None:
            self._spawn(self._enroller.forget(participant.identity))
        self._recompute_permissions()

    def on_attributes_changed(
        self, changed_attributes: dict[str, str], participant: rtc.Participant
    ) -> None:
        if "language" not in changed_attributes:
            return
        self._cancel_enrollment(participant.identity)
        existing = self._sessions.pop(participant.identity, None)
        if existing is not None:
            logger.info(
                "language changed for %s; restarting translation session", participant.identity
            )
            self._spawn(self._close_session(existing, drain=False))
        self._spawn(self._ensure_session(participant.identity))

    def on_local_track_published(
        self, publication: rtc.LocalTrackPublication, track: rtc.LocalTrack
    ) -> None:
        if publication.kind != rtc.TrackKind.KIND_AUDIO:
            return
        target = target_language_from_track_name(publication.name)
        if target is None:
            return
        self._translated_tracks[publication.sid] = target
        self._recompute_permissions()

    def on_local_track_unpublished(self, publication: rtc.LocalTrackPublication) -> None:
        if self._translated_tracks.pop(publication.sid, None) is not None:
            self._recompute_permissions()

    # ---------------------------------------------------------------- sessions

    def _spawn(self, coro: object) -> None:
        task = asyncio.ensure_future(coro)  # type: ignore[arg-type]
        self._tasks.add(task)  # type: ignore[arg-type]
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("translation session task failed: %s", exc, exc_info=exc)

    async def _ensure_session(self, identity: str) -> None:
        if self._closed or identity in self._sessions:
            return

        participant = self._ctx.room.remote_participants.get(identity)
        if participant is None:
            return

        try:
            source_language = validate_language(participant.attributes.get("language"))
            target = self._pair.partner(source_language)
        except UnsupportedLanguageError as exc:
            logger.warning("participant %s has no usable language: %s", identity, exc)
            await self._send_status(
                identity, {"type": "language_error", "message": str(exc)}
            )
            return

        room_options = room_io.RoomOptions(
            audio_input=True,
            text_output=True,
            text_input=False,  # multi-session text input is not supported; UI uses status data
            participant_identity=identity,
            close_on_disconnect=False,
            delete_room_on_close=False,
            audio_output=room_io.AudioOutputOptions(
                track_name=track_name_for(target),
            ),
        )

        session = None
        try:
            session, agent = build_session(source_language, self._pair, self._config)
            session.on("error", lambda ev, ident=identity: self._on_session_error(ident, ev))
            await session.start(agent=agent, room=self._ctx.room, room_options=room_options)
        except Exception as exc:  # noqa: BLE001 - contain any startup failure per participant
            logger.error("failed to start session for %s: %s", identity, exc, exc_info=True)
            await self._send_status(
                identity,
                {
                    "type": "session_start_error",
                    "message": safe_error_message(
                        exc, (self._config.livekit_api_secret, self._config.livekit_api_key)
                    ),
                },
            )
            if session is not None:
                await self._close_session(session, drain=False)
            return

        self._sessions[identity] = session
        self._recompute_permissions()
        await self._send_status(
            identity,
            {
                "type": "session_ready",
                "pair": self._pair.code,
                "source_language": source_language,
                "target_language": target,
            },
        )
        logger.info(
            "translation session ready for %s (%s -> %s, pair=%s)",
            identity,
            source_language,
            target,
            self._pair.code,
        )
        self._maybe_start_enrollment(identity, source_language, session, participant)

    # -------------------------------------------------------- voice enrollment

    def _maybe_start_enrollment(
        self,
        identity: str,
        source_language: str,
        session: object,
        participant: rtc.Participant,
    ) -> None:
        """Kick off per-participant voice cloning when enabled and consented."""
        if self._enroller is None or not has_voice_consent(participant.attributes):
            return

        cached = self._enroller.get(identity)
        if cached is not None:
            # Returning participant: reuse the clone, no new sample needed.
            if self._apply_cloned_voice(session, cached.voice_id):
                self._spawn(self._send_status(identity, {"type": "voice_cloned"}))
            return

        task = asyncio.ensure_future(
            self._enroll_voice(identity, source_language, session)
        )
        self._tasks.add(task)  # type: ignore[arg-type]
        self._enroll_tasks[identity] = task

        def _on_done(t: asyncio.Task[None], ident: str = identity) -> None:
            self._tasks.discard(t)  # type: ignore[arg-type]
            if self._enroll_tasks.get(ident) is t:
                del self._enroll_tasks[ident]
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.error("voice enrollment task failed: %s", exc, exc_info=exc)

        task.add_done_callback(_on_done)

    def _cancel_enrollment(self, identity: str) -> None:
        task = self._enroll_tasks.pop(identity, None)
        if task is not None and not task.done():
            task.cancel()

    async def _enroll_voice(self, identity: str, source_language: str, session: object) -> None:
        """Capture a sample, clone it, and swap the session to the cloned voice.

        Every failure path logs and reports ``voice_cloning_error`` so the
        session simply keeps its standard fallback voice.
        """
        assert self._enroller is not None
        try:
            voice = self._enroller.get(identity)
            if voice is None:
                wav = await self._capture_sample(identity)
                if wav is None:
                    logger.info(
                        "no usable voice sample for %s; keeping the standard voice", identity
                    )
                    return
                voice = await self._enroller.enroll(
                    identity, language=source_language, wav=wav
                )
            if voice is None or not self._apply_cloned_voice(session, voice.voice_id):
                await self._send_status(
                    identity,
                    {
                        "type": "voice_cloning_error",
                        "message": "Voice cloning is unavailable; using a standard voice.",
                    },
                )
                return
            await self._send_status(identity, {"type": "voice_cloned"})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - enrollment must never take the session down
            logger.error("voice enrollment failed for %s", identity, exc_info=True)
            await self._send_status(
                identity,
                {
                    "type": "voice_cloning_error",
                    "message": "Voice cloning failed; using a standard voice.",
                },
            )

    async def _capture_sample(self, identity: str) -> bytes | None:
        """Record the participant's first seconds of clear speech as a WAV."""
        participant = self._ctx.room.remote_participants.get(identity)
        if participant is None:
            return None
        track = await wait_for_audio_track(
            participant, timeout_seconds=TRACK_WAIT_SECONDS
        )
        if track is None:
            logger.info("no subscribed audio track for %s; cannot enroll voice", identity)
            return None
        return await collect_enrollment_sample(
            track,
            target_seconds=self._config.clone_sample_seconds,
            deadline_seconds=self._config.clone_timeout_seconds,
        )

    def _apply_cloned_voice(self, session: object, voice_id: str) -> bool:
        """Swap a session's TTS to the cloned voice; False when unsupported."""
        tts_node = getattr(session, "tts", None)
        if isinstance(tts_node, DynamicVoiceTTS):
            return tts_node.set_cloned_voice(voice_id)
        logger.warning(
            "session has no dynamic TTS; cloned voice %s not applied", voice_id
        )
        return False

    async def _close_session(self, session: object, *, drain: bool) -> None:
        try:
            if drain:
                await asyncio.wait_for(session.drain(), timeout=10)  # type: ignore[attr-defined]
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("session drain timed out; closing immediately")
        except Exception:  # noqa: BLE001 - teardown must not raise
            logger.warning("session drain failed", exc_info=True)
        try:
            await session.aclose()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.warning("session close failed", exc_info=True)

    def _on_session_error(self, identity: str, ev: object) -> None:
        error = getattr(ev, "error", ev)
        source = getattr(ev, "source", None)
        stage = type(source).__name__ if source is not None else "unknown"
        # Log full detail server-side (never forwarded verbatim to clients).
        logger.error("pipeline error for %s [stage=%s]: %s", identity, stage, error, exc_info=error)
        self._spawn(
            self._send_status(
                identity,
                {
                    "type": "pipeline_error",
                    "stage": stage,
                    "message": safe_error_message(
                        error, (self._config.livekit_api_secret, self._config.livekit_api_key)
                    ),
                },
            )
        )

    # ------------------------------------------------------------- routing/SFU

    def _recompute_permissions(self) -> None:
        """Restrict every translated track to participants of its target language."""
        permissions: list[rtc.ParticipantTrackPermission] = []
        for identity, participant in self._ctx.room.remote_participants.items():
            try:
                their_language = validate_language(participant.attributes.get("language"))
            except UnsupportedLanguageError:
                continue
            allowed_sids = [
                sid
                for sid, target in self._translated_tracks.items()
                if target == their_language
            ]
            permissions.append(
                rtc.ParticipantTrackPermission(
                    participant_identity=identity,
                    allow_all=False,
                    allowed_track_sids=allowed_sids,
                )
            )
        try:
            self._ctx.room.local_participant.set_track_subscription_permissions(
                allow_all_participants=False,
                participant_permissions=permissions,
            )
        except Exception:  # noqa: BLE001 - permissions are best-effort, never fatal
            logger.warning("failed to update track subscription permissions", exc_info=True)

    # ------------------------------------------------------------------ status

    async def _send_status(self, identity: str, payload: dict[str, str]) -> None:
        try:
            await self._ctx.room.local_participant.publish_data(
                json.dumps(payload),
                topic=STATUS_TOPIC,
                destination_identities=[identity],
            )
        except Exception:  # noqa: BLE001 - status delivery must never break the pipeline
            logger.warning("could not deliver interpreter status to %s", identity, exc_info=True)


__all__ = ["InterpreterManager", "STATUS_TOPIC", "safe_error_message"]
