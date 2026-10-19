# Task 03 — Python LiveKit Agent Core

## Goal

Implement the basic agent lifecycle, participant language registration and pure language-routing logic.

## Requirements

1. Use the current LiveKit Agents APIs documented for the installed SDK version.
2. Connect the agent to a LiveKit room and handle participant join/leave events.
3. Require or validate a participant language of `bn` or `en`; do not rely only on automatic language detection when a participant has selected a language.
4. Implement a small, independently testable routing function:
   - `bn` source → `en` destination.
   - `en` source → `bn` destination.
   - Reject unsupported/missing language values with a clear error.
5. Keep source participant identity and intended recipient identity available to the routing layer.
6. Subscribe only to original microphone/source tracks for transcription. Do not re-ingest translated tracks.
7. Keep session lifecycle, routing and translation logic separate.
8. Publish useful agent/session state for the frontend through the supported mechanism chosen by the application. Do not expose credentials.
9. Handle participant departure and session cleanup without leaking tasks or resources.

## Translation prompt

Create a prompt equivalent in intent to:

```text
You are a real-time Bengali-English meeting interpreter.

Translate the speaker's message faithfully into the requested target language.
- If the source is Bengali, output natural, professional English.
- If the source is English, output natural, professional Bengali.
- Preserve names, company names, dates, numbers, amounts, and technical terms.
- Preserve intent, tone, and politeness.
- Do not answer questions or add explanations.
- Return only the translated text.
```

Pass source and target language explicitly to each translation request. Keep the prompt in `agent/prompts.py`, not embedded throughout room-handling code.

## Deliverables

- Agent entry point and session lifecycle.
- Language validation and routing module.
- Translation prompt/helper module.
- Unit tests for `bn → en`, `en → bn`, and invalid language values.
- Safe session status/error handling.

## Acceptance checks

- Agent starts with valid configuration and fails clearly with invalid configuration.
- Language routing is deterministic and unit-tested.
- Participant join/leave events are handled.
- Translated output is never treated as source microphone input.
