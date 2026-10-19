# Task 02 — Repository Scaffold, Dependencies and Configuration

## Goal

Prepare a maintainable Python agent project and Next.js UI area without implementing the full interpretation pipeline yet.

## Instructions

1. Inspect the existing repository. Preserve existing structure and conventions where reasonable.
2. If starting from scratch, create the project structure described in `00_MASTER_INSTRUCTIONS.md`.
3. Set up a Python virtual environment and dependency configuration using current LiveKit Agents documentation and the model plugins selected in Task 01.
4. Create `.env.example` with:
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `STT_MODEL`
   - `LLM_MODEL`
   - `TTS_MODEL`
   - `BENGALI_LANGUAGE=bn`
   - `ENGLISH_LANGUAGE=en`
5. Load environment variables through a dedicated configuration module. Validate required settings at startup and provide safe, actionable errors for missing configuration.
6. Ensure `.env` is ignored by Git. Never put credentials in Next.js public environment variables or client bundles.
7. Add basic formatting, linting and test commands appropriate to the selected project tooling.
8. Create only lightweight placeholders for agent/UI modules if needed; do not implement later tasks prematurely.

## Suggested Python module responsibilities

- `agent/main.py`: LiveKit Agents entry point.
- `agent/config.py`: environment parsing and validation.
- `agent/session.py`: room/session lifecycle.
- `agent/routing.py`: source language and intended recipient mapping.
- `agent/translation.py`: translation orchestration.
- `agent/prompts.py`: translation prompt templates.

## Deliverables

- Dependency/project configuration.
- `.env.example` and `.gitignore`.
- Configuration validation code and tests.
- Minimal `README.md` setup section.
- `docs/model-validation.md` from Task 01.

## Acceptance checks

- A clean checkout can follow the documented environment setup.
- Missing required configuration fails clearly and safely.
- Secret values are not logged or exposed to the frontend.
- Tests for configuration validation pass.
