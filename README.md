# Bengali <-> English Meeting Interpreter

A real-time bidirectional meeting interpreter built with [LiveKit Agents](https://docs.livekit.io/agents/) (Python) and a Next.js (TypeScript) web client. For each remote participant, the agent creates a dedicated translation session that hears their speech in their selected language and publishes translated audio into the room under `translated-<target>`; SFU-level track subscription permissions ensure each participant only receives translations into their selected language.

## Architecture

- **Agent (Python)**: One `AgentSession` per source participant inside a shared room job (`agent/session.py`). Audio is filtered to the linked source via RoomIO participant filtering; each session publishes translated output to a named track `translated-<lang>`. `InterpreterManager` recomputes SFU subscription permissions whenever translated tracks are published/unpublished or a participant's `language` attribute changes, so participants with `language=en` only receive `translated-en` tracks (and `bn` only `translated-bn`).
- **Pipeline**: STT -> LLM -> TTS per session (`agent/translation.py`), all served through **LiveKit Inference** (no separate provider API keys). Defaults: Deepgram Nova-3 (`deepgram/nova-3`) for `bn`/`en`, `openai/gpt-4o-mini`, Cartesia Sonic-3 (`cartesia/sonic-3`) with separate voices per target language. See `docs/model-validation.md` for selection rationale, rejected candidates, and pricing.
- **Routing / prompts**: `agent/routing.py` is pure logic (language validation, `bn <-> en` direction, `translated-<lang>` track naming). `agent/prompts.py` enforces "return only the translated text" with preservation of names/dates/numbers/amounts/technical terms and intent/tone/politeness, and no answers or explanations.
- **Web client (Next.js App Router)**: `web/app/page.tsx` lets users pick an identity and language (`bn`/`en`), requests a token from `POST /api/token` (with `language` in participant attributes), joins the room, and renders remote audio via `RoomAudioRenderer`. It displays status messages the agent publishes on the `interpreter-status` data topic (addressed to the local identity only).
- **Security**: secrets never appear in logs or client-facing status messages; `safe_error_message` redacts `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` and common secret markers, and pipeline errors are logged in full server-side while participants only receive a redacted message.

## Repository layout

```
agent/            Python package: main (entry point), config, session (InterpreterManager),
                  translation (pipeline), routing, prompts, native_compat (AVX2 shim)
tests/            pytest suite (config, routing, prompts) + AVX2-safe conftest shim
web/              Next.js client (App Router), see web/README.md
docs/             Model validation notes (docs/model-validation.md)
doc/              Ordered implementation pack (task files 00..07) used to build this repo
.env.example      Agent environment template
web/.env.example  Web environment template
pyproject.toml    Python deps, pytest and ruff configuration
opencode.json     Agent tooling config (LiveKit docs MCP server)
```

## Requirements

- **Python 3.12** (`.python-version`; `requires-python >= 3.10`). The bundled native VAD/EOT in `livekit-local-inference` requires AVX2; on CPUs without it the module is replaced by a shim (`agent/native_compat.py`) and the agent falls back to STT-based turn detection, so it runs (with slightly less accurate endpointing) on older hardware.
- **Node.js 20+** and npm (for the web client).
- A **LiveKit Cloud project** (or self-hosted LiveKit server) with API key/secret and Inference enabled.
- Environment variables via `.env` (agent) and `web/.env.local` (web).

## Quickstart

### 1) Agent (Python)

```bash
# Install dependencies with uv
uv sync

# Copy and configure environment
cp .env.example .env
# Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
# Optionally override STT_MODEL / LLM_MODEL / TTS_MODEL, voices, AGENT_NAME

# Run tests and lint
uv run pytest -q        # 54 tests
uv run ruff check .

# Local development worker
uv run python -m agent.main dev

# Production worker (LiveKit Cloud agent deployment)
uv run python -m agent.main start
```

`agent/main.py` loads config (failing fast with variable *names* only), registers an `AgentServer` whose `agent_name` comes from `AGENT_NAME` (default `bengali-english-interpreter`), and for each room creates an `InterpreterManager` that spawns one `AgentSession` per remote participant based on their `language` attribute. Sessions restart when that attribute changes and are closed on disconnect.

### 2) Web client (Next.js)

```bash
cd web
npm install
cp .env.example .env.local
# Set NEXT_PUBLIC_LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
# (same LiveKit project as the agent) and optionally LIVEKIT_ROOM_NAME / AGENT_NAME

npm run dev
# Open http://localhost:3000
```

Join with an identity and select your language, then press **Start speaking (unmute)** to publish your microphone - the agent can only translate audio from participants who are unmuted:

- **English** -> receives Bengali translation (`translated-en` tracks)
- **Bengali** -> receives English translation (`translated-bn` tracks)

Token endpoint contract: `POST /api/token` with `{ identity, language: "bn"|"en", room? }` returns `{ token, url }`. The route validates the inputs, embeds `language` in the participant attributes, dispatches the `AGENT_NAME` worker (deduplicated so a room never runs two interpreter jobs) and grants room join plus subscribe/publish/data. `room` defaults to `LIVEKIT_ROOM_NAME` (`interpreter-room`), so every participant of a meeting lands in the same room.

## Configuration

Agent variables (`.env.example`, parsed by `agent/config.py`):

| Variable | Default | Notes |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | — | required; missing names are reported, values never are |
| `STT_MODEL` | `deepgram/nova-3` | LiveKit Inference model ID |
| `LLM_MODEL` | `openai/gpt-4o-mini` | LiveKit Inference model ID |
| `TTS_MODEL` | `cartesia/sonic-3` | LiveKit Inference model ID |
| `TTS_VOICE_BN` | `f786b574-daa5-4673-aa0c-cbe3e8534c02` | Cartesia voice for Bengali output |
| `TTS_VOICE_EN` | `9626c31c-bec5-4cca-baa8-f8ba9e84c8bc` | Cartesia voice for English output |
| `BENGALI_LANGUAGE` / `ENGLISH_LANGUAGE` | `bn` / `en` | do not change without updating the whole app |
| `AGENT_NAME` | `bengali-english-interpreter` | worker registration / dispatch name |
| `TOKEN_TTL_SECONDS` | `3600` | must be a positive integer |

Web variables (`web/.env.example`):

- `NEXT_PUBLIC_LIVEKIT_URL` (client-visible room URL; also used by the token route when `LIVEKIT_URL` is unset)
- `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (server-side token generation only)
- `LIVEKIT_ROOM_NAME` (optional, default `interpreter-room`) - the shared meeting room
- `AGENT_NAME` (optional, default `bengali-english-interpreter`) - must match the agent's `AGENT_NAME`
- `TOKEN_TTL_SECONDS` (optional, default `3600`)

The web client must point at the **same LiveKit project** as the agent, otherwise the dispatch lands in a project with no registered worker and no translation session starts.

## Testing

```bash
uv run pytest -q      # tests/test_config.py, test_routing.py, test_prompts.py
uv run ruff check .   # line length 100, rules: E, F, I, W, UP, B (web/ and docs/ excluded)

cd web && npm run build   # compiles the Next.js client and type-checks /api/token
```

`tests/conftest.py` calls `agent.native_compat.install_compat_shim()`, which probes AVX2 and installs the placeholder module when the CPU lacks it, so the suite never loads the native VAD/EOT modules.

## Documentation

- `docs/model-validation.md` - model/voice selection evidence, rejected candidates, Inference pricing and quota caveats (dated 2026-10-19).
- `doc/` - the original ordered implementation pack (`00_MASTER_INSTRUCTIONS.md` .. `07_RUNBOOK_AND_HANDOFF.md`) with product requirements and acceptance criteria.
- `web/README.md` - web client setup and routing details.

## Notes

- **Native inference on CPUs without AVX2**: importing `livekit.agents` eagerly loads `livekit.local_inference`, whose `_native.pyd` faults with `0xc000001d` (illegal instruction) on pre-Haswell CPUs — the process dies with no log output. `agent/native_compat.py` detects AVX2 (or honours `INTERPRETER_STUB_LOCAL_INFERENCE=1`) and pre-registers a placeholder module, so imports succeed and `build_session` disables the native VAD in favour of `turn_detection="stt"`. On AVX2-capable hardware the bundled silero VAD and end-of-turn model are used unchanged. Native VAD/EOT still cannot be used without AVX2.
- **`TTS provider completed without producing audio`**: Cartesia returns this (wrapped as `CONNECTION_ERROR`) when `TTS_VOICE_BN` / `TTS_VOICE_EN` is not an exact ID from the Cartesia voice library — a single wrong character is enough. Voice IDs here are `f786b574-daa5-4673-aa0c-cbe3e8534c02` (bn) and `9626c31c-bec5-4cca-baa8-f8ba9e84c8bc` (en); check them against `docs/model-validation.md` before changing.
- **Routing**: `target_language_from_track_name` only accepts valid `bn`/`en`; unknown or missing `language` attributes produce a `language_error` status instead of a session.
- **Error containment**: session/pipeline failures are logged server-side with full detail and surfaced only to the affected participant as redacted status messages on the `interpreter-status` topic (`session_ready`, `language_error`, `session_start_error`, `pipeline_error`).
- **Feedback loop**: each session hears only its linked source participant, so translated output is never re-ingested as source audio.
- **Agent dispatch**: the token route dispatches the worker only when the room has no dispatch for `AGENT_NAME` (and the token itself carries a `roomConfig.agents` entry that LiveKit applies when it creates the room). Two jobs in the same room would each publish translated audio, so duplicate dispatches are avoided deliberately.
- **License**: not yet declared (`pyproject.toml` and `web/package.json` carry no license field and the repo has no `LICENSE` file).
