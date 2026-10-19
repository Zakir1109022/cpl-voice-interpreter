# Task 06 — Automated Tests and End-to-End Acceptance

## Goal

Verify the application against the behavior required for a bidirectional Bengali-English interpreter.

## Automated tests

Add or complete tests for:

- Language validation accepts only `bn` and `en`.
- Routing maps `bn → en` and `en → bn`.
- Unsupported language values are rejected.
- Translation prompt instructs the model to preserve names, dates, numbers, amounts, technical terms, intent and tone.
- Translation output is expected to contain only the translated text, without explanations.
- Configuration validation catches missing required settings without exposing secrets.
- Routing prevents sending translated audio to the source participant or an unrelated participant, to the extent testable with the chosen architecture.
- Error handling for STT, LLM, TTS and participant disconnects.

Use mocks for external model calls in unit tests. Do not require paid inference calls for the default test suite.

## Manual end-to-end test plan

1. Join a room with two participants.
2. Set one participant to Bengali (`bn`) and the other to English (`en`).
3. Speak a short Bengali sentence. Confirm English transcription/translation/audio reaches the English participant.
4. Speak a short English sentence. Confirm Bengali transcription/translation/audio reaches the Bengali participant.
5. Confirm the source speaker does not hear their translated output fed back as new input.
6. Test names, dates, numbers, amounts and technical vocabulary.
7. Interrupt a long utterance and confirm stale queued audio is cancelled where supported.
8. Mute/unmute each participant.
9. Disconnect and reconnect one participant.
10. Make a model unavailable or simulate a quota error; confirm a useful error is shown and the meeting does not crash globally.
11. Confirm raw audio is not stored by default.
12. Run the test suite, linter and type checks available in the repository.

## Acceptance criteria

- Both directions work in the same room.
- Each translated stream reaches only its intended recipient.
- Translation preserves core meaning and key details in representative test cases.
- Mute, reconnect and participant departure are handled.
- Model/quota errors are clear and safe.
- No secrets appear in logs or browser bundles.
- Current model support, API assumptions and pricing/usage caveats are documented.

## Report

Record commands run, test results, known limitations and any manual checks that require LiveKit credentials or real participants.
