# Bengali ↔ English AI Meeting Interpreter — Coding-Agent Implementation Pack

This folder divides the implementation plan into small, ordered tasks for a coding agent. Implement one file at a time, in sequence, and run the stated checks before moving on.

## Product goal

Build a web meeting application where:
- Bengali-speaking participants hear translated English audio.
- English-speaking participants hear translated Bengali audio.
- Original and translated audio remain distinct.
- Translated audio is routed only to the intended recipient.
- The Python agent uses LiveKit Agents and LiveKit Inference; the meeting UI uses Next.js.

## Task order

1. `00_MASTER_INSTRUCTIONS.md` — rules and overall acceptance criteria.
2. `01_MODEL_VALIDATION.md` — confirm supported STT/TTS/LLM models before implementation.
3. `02_REPOSITORY_AND_CONFIG.md` — scaffold, dependencies, configuration, secrets.
4. `03_PYTHON_AGENT_CORE.md` — room lifecycle, participant language, translation and routing.
5. `04_BIDIRECTIONAL_AUDIO.md` — complete both translation directions and interruption handling.
6. `05_NEXTJS_MEETING_UI.md` — join/create room, language selection, token integration and UI status.
7. `06_TESTING_AND_ACCEPTANCE.md` — tests, end-to-end validation, reliability and cost checks.
8. `07_RUNBOOK_AND_HANDOFF.md` — local setup, run commands, README and handoff notes.

## How to use with a coding agent

- Open the repository root in your coding agent.
- Give it `00_MASTER_INSTRUCTIONS.md` first.
- Then provide one numbered task file at a time.
- Tell the agent to inspect the current repository before editing, implement only the current task, run relevant checks, and summarize changed files plus test results.
- Do not proceed to the next task if the current task has failing checks or unresolved model compatibility.
- The exact LiveKit SDK APIs and model/plugin identifiers must be verified against the current official docs; do not invent API names or assume model availability.

## Architecture constraints

- Python + LiveKit Agents for the interpreter.
- LiveKit Cloud for real-time rooms and audio transport.
- LiveKit Inference for hosted STT, LLM and TTS where supported.
- Next.js for the meeting UI.
- Bengali language code: `bn`; English language code: `en`.
- Keep credentials server-side and out of browser bundles.
- Do not capture translated output as source input; avoid audio feedback loops.
- Do not store sensitive audio by default.

## Official documentation

- https://docs.livekit.io/agents/
- https://docs.livekit.io/agents/models/inference/
- https://docs.livekit.io/agents/models/stt/
- https://docs.livekit.io/agents/models/tts/
- https://livekit.com/pricing/inference
