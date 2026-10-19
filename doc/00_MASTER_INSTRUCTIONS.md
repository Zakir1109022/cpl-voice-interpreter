# Task 00 — Master Instructions for the Coding Agent

## Objective

Implement a real-time, bidirectional Bengali ↔ English meeting interpreter using Python, LiveKit Agents, LiveKit Cloud, LiveKit Inference and a Next.js web UI.

## Required user experience

1. A participant creates or joins a meeting.
2. Each participant selects their spoken language: Bengali (`bn`) or English (`en`).
3. Bengali speech is transcribed in Bengali, translated into English, synthesized as English audio and delivered to the English-speaking participant.
4. English speech is transcribed in English, translated into Bengali, synthesized as Bengali audio and delivered to the Bengali-speaking participant.
5. Participants can mute/unmute, see connection and agent status, and optionally see source/translated captions.
6. A participant must not receive their own translated audio as microphone input.
7. Model, connection and quota failures should be reported without exposing credentials or crashing the entire meeting.

## Required implementation principles

- Inspect the repository and existing conventions before making changes.
- Keep configuration, room/session lifecycle, language routing, translation prompts and UI concerns separate.
- Use official, current LiveKit documentation to confirm SDK APIs, plugins, model identifiers and language support.
- Make STT, LLM and TTS model identifiers configurable. Do not hard-code model availability or claim a model is free without verification.
- Confirm that STT and TTS options support both Bengali and English before implementing the full pipeline.
- Prefer streaming/session-based processing and phrase/turn boundaries where supported. Do not send an HTTP request for every tiny audio frame.
- Cancel obsolete queued or active speech after an interruption where the SDK/model supports it.
- Route translated tracks only to the intended recipient.
- Do not store raw audio by default.
- Never put `LIVEKIT_API_SECRET` or other server credentials in client-side code.
- Follow the repository's package manager, linting and testing conventions. Avoid unrelated refactors.

## Expected repository areas

Adapt to the repository if it already exists. If it is new, use a clear structure similar to:

```text
meeting-interpreter/
├── agent/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── session.py
│   ├── routing.py
│   ├── translation.py
│   └── prompts.py
├── web/
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Definition of done

- Both translation directions work in one LiveKit room.
- Each translated stream reaches only its intended recipient.
- Names, company names, dates, numbers, amounts and technical terms are preserved as well as practical.
- Mute, disconnect, reconnect, interruption and participant departure are handled.
- Model/API/quota errors are visible and do not expose secrets.
- Automated tests cover language routing and translation prompt behavior.
- Setup and run instructions are documented.
- Current model support and pricing assumptions are explicitly verified or listed as unresolved blockers.

## Required response after each task

Report:
1. What changed.
2. Files created or modified.
3. Commands/tests executed and their results.
4. Any unresolved issue or decision that blocks the next task.

Do not silently skip a requirement. If the existing SDK or selected model cannot meet a requirement, explain the limitation and propose the smallest compatible adjustment.
