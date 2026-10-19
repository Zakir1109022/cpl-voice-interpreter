# Task 04 — Bidirectional Speech-to-Speech Interpretation

## Goal

Connect STT, translation and TTS into both directions, then route generated speech to the correct participant.

## Direction A: Bengali → English

1. Capture the Bengali participant's original microphone track.
2. Transcribe Bengali audio to Bengali text with a validated STT model.
3. Translate the text to natural, professional English.
4. Generate English speech with a validated English-capable TTS model.
5. Deliver translated audio only to the English-speaking recipient.

## Direction B: English → Bengali

1. Capture the English participant's original microphone track.
2. Transcribe English audio to English text with a validated STT model.
3. Translate the text to natural, professional Bengali.
4. Generate Bengali speech with a validated Bengali-capable TTS model.
5. Deliver translated audio only to the Bengali-speaking recipient.

## Audio and latency requirements

- Use persistent LiveKit tracks and streaming/session-based processing where supported.
- Do not issue a separate HTTP request for every tiny audio frame.
- Use voice activity detection and phrase/turn boundaries to avoid translating incomplete fragments.
- Stream translated output where supported by the selected model and SDK.
- Cancel queued or active translated speech when it becomes obsolete after an interruption, where supported.
- Start by prioritizing accurate, short phrases; optimize latency after correctness is established.
- Prevent translated audio from entering the source transcription pipeline.
- Keep the two directions independent so one direction's failure does not unnecessarily stop the other.

## Routing and safety

- Every translated output must be associated with a source participant and a target recipient.
- Never broadcast translated audio to unintended participants.
- Keep original audio distinct from translated audio.
- Do not store raw audio by default.
- Report STT/LLM/TTS errors and quota exhaustion without leaking secrets.

## Implementation notes

Use current LiveKit Agents APIs for room sessions, track subscriptions, model plugins and audio publication. Confirm exact calls in the official documentation for the installed version. Do not invent method names. If direct per-participant track routing is not supported by the chosen approach, document and implement the closest supported design without violating recipient privacy.

## Deliverables

- Working Bengali-to-English path.
- Working English-to-Bengali path.
- Recipient-only translated audio routing.
- Interruption, cancellation, reconnect and cleanup handling where supported.
- Logs/metrics for stage latency and failures without raw audio content.

## Acceptance checks

- Bengali speech produces English audio for the English participant.
- English speech produces Bengali audio for the Bengali participant.
- Original speaker does not receive their own translation as input.
- Concurrent activity, interruptions and participant departure do not create persistent audio loops or stale playback.
