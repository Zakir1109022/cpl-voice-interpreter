# Plan: Per-Participant Dynamic Voice Preservation

## Goal

Instead of one predefined TTS voice per target language, each participant's translations are
synthesized in a voice cloned from **their own speech**, so listeners hear the same voice
identity across the language barrier. Decisions confirmed with the user:

- **Approach:** zero-shot voice-cloning TTS via an external provider.
- **Sample capture:** automatic from the participant's live speech (no manual enrollment step).
- **Privacy:** external cloning allowed, with a consent notice in the UI.

Honest scope: we preserve **voice identity/timbre** cross-lingually. Intonation/prosody of the
original utterance is not transferred (research-grade); the clone speaks with the TTS's own prosody.

## Provider choice

**Cartesia instant voice cloning** (keeps the project on Cartesia, which is already the TTS stack):

| Requirement | Cartesia sonic-3 | Fish Audio s2.1 | LiveKit Custom Voices |
|---|---|---|---|
| Output language `ja` | yes | yes | yes |
| Output language `bn` | **yes** | **no** | via cloned provider |
| Programmatic runtime clone | **yes** (REST API) | yes | **no** (dashboard only) |
| Existing usage in repo | yes (`agent/config.py:15`) | no | no |

Important LiveKit constraint ([custom voices docs](https://docs.livekit.io/agents/models/tts/custom-voices),
[Cartesia docs](https://docs.livekit.io/agents/models/tts/cartesia)): custom/cloned voices are **not
available through LiveKit Inference**. When cloning is enabled, the agent must use the
**Cartesia plugin** (`livekit-plugins-cartesia`, own `CARTESIA_API_KEY`) instead of
`inference.TTS`. Synthesis for non-cloned fallback sessions can stay on LiveKit Inference.

**Spike first (half day, before main build):**
1. Create an instant clone from a ~10–30s Bengali sample via Cartesia API; measure clone latency.
2. Synthesize Japanese and Bengali test sentences with that clone; listen for identity retention
   cross-lingually (bn reference → ja output, ja reference → bn output).
3. Confirm per-clone cost and rate limits. If quality is unacceptable, fall back to plan B:
   ElevenLabs instant clone (verify `bn` output support on the chosen model) — same architecture,
   different client module.

## Architecture

```
participant mic ──► LiveKit room ──┬──► RoomIO → STT → LLM(translate) → TTS(cloned voice) → translated-<lang> track
                                   │
                                   └──► AudioStream tap (new) → enrollment buffer (first ~15s of
                                        VAD-gated speech) → Cartesia clone API → voice_id/embedding
                                        (cached per identity) ──────────────┘
```

- The agent already subscribes `AUDIO_ONLY` (`agent/main.py:98`) and each interpreter session is
  pinned to one source participant (`agent/session.py:169-179`). We add a second reader
  (`rtc.AudioStream` on the same remote track — LiveKit permits multiple local readers) that only
  feeds the enrollment buffer, never the STT pipeline.
- Until a clone is ready, utterances are translated with the current per-language fallback voice
  (existing behavior). When the clone completes, subsequent turns use the cloned voice
  (`session.tts.update_options(voice=...)` or session rebuild — verify API in spike).

## Work items

### 1. `agent/voice_enroll.py` (new)

- `EnrollmentBuffer`: accumulates PCM frames from an `AudioStream`, applies simple
  energy/VAD gating (reuse the session VAD or an RMS threshold), target ~15s of clean speech,
  hard cap 30s / timeout 90s.
- `VoiceEnroller`:
  - `async enroll(identity, frames) -> ClonedVoice | None` — encodes 16kHz mono WAV, calls
    Cartesia clone REST API (`POST /voices/clone`), returns voice id + embedding.
  - In-memory cache `identity -> ClonedVoice` per room; optional persistence hook
    (env-disabled file/KV store) so rejoiners skip re-cloning.
  - Failures/timeouts return `None` → caller keeps fallback voice. Never blocks translation.

### 2. `agent/session.py`

- On `participant_connected` / `local_track_subscribed`, start the enrollment tap for that
  identity (skip agents, skip participants whose consent attribute is not granted).
- Hold `VoiceRegistry` on `InterpreterManager`; when a clone becomes ready, update the linked
  session's TTS voice.
- Keep `_recompute_permissions` and track naming unchanged.

### 3. `agent/translation.py`

- `build_session(...)` gains optional `voice: ClonedVoice | None` and `tts_mode` ("inference" |
  "cartesia-plugin").
- When cloned voice present → `cartesia.TTS(model="sonic-3", voice=cloned.voice_id or embedding,
  language=target)`; else current `inference.TTS(...)` path (`agent/translation.py:64-68`).

### 4. `agent/config.py`

New env keys (with `.env.example` entries):
- `VOICE_CLONING_ENABLED` (default false)
- `CARTESIA_API_KEY`
- `CLONE_SAMPLE_SECONDS` (default 15), `CLONE_TIMEOUT_SECONDS` (default 90)
- Existing `TTS_VOICE_*` become the **fallback** voices; rename accessor doc only, no breaking
  key changes.

### 5. `pyproject.toml`

- Add optional extra: `livekit-agents[cartesia]~=1.8`. Import guarded so the app runs without the
  plugin when cloning is disabled.

### 6. Web (`web/`)

- Consent: token route (`web/app/api/token/route.ts`) accepts `voiceConsent: true` and stamps
  participant attribute `voice_cloning_consent: "true"`; agent only enrolls consenting users.
- UI (`web/app/page.tsx`): consent checkbox on join screen ("Allow your voice to be used to
  create a translated voice that sounds like you"), plus a per-participant indicator
  "Voice cloning: on/off/fallback".
- Update the footer disclaimer text (`page.tsx:439`).

### 7. Tests

- `tests/test_voice_enroll.py`: buffer gating, cap/timeout, WAV encoding, cache hit/miss,
  clone API failure → `None` (mock httpx).
- Extend `tests/test_config.py` for new env keys and disabled-by-default behavior.
- Extend `tests/test_session.py`-level tests: consent attribute required before tap starts;
  fallback voice used until clone ready.

### 8. Docs

- README: new env vars, consent flow, latency expectations (first ~1–2 utterances use fallback
  voice while the clone is created).
- `doc/04_BIDIRECTIONAL_AUDIO.md`: enrollment tap design, "do not store raw audio beyond the
  enrollment window" note aligned with existing privacy guidance.

## Behavior summary

1. Participant joins with consent attribute → agent taps their audio.
2. After ~15s of clear speech, clone is created (one-time per participant, per room or cached).
3. Subsequent translated speech for that participant is synthesized in their cloned voice;
   listeners on `translated-<lang>` hear the same voice identity for every speaker.
4. Any failure (no consent, timeout, API error) degrades gracefully to today's fixed voices.

## Risks

- **Cross-lingual clone quality** (bn voice speaking Japanese) — mitigated by the spike and the
  ElevenLabs fallback plan.
- **Clone latency** delays first cloned turn — acceptable; fallback covers it.
- **Cartesia plugin vs Inference dual-path** adds a TTS construction branch — isolated in
  `translation.py`.
- **Consent/abuse:** cloning requires explicit per-participant consent; samples kept only in
  memory for the enrollment window; clone cache cleared when the room ends (unless persistence
  explicitly enabled).
- **Cost:** per-clone charge + same synthesis rates; document in README.

## Verification

- Unit tests above (`pytest`).
- Manual: two browser tabs, one bn speaker + one ja listener; confirm listener hears two
  distinct voices matching the two speakers after enrollment window; confirm non-consenting tab
  gets fallback voice; kill Cartesia key → graceful fallback, no dropped translations.
