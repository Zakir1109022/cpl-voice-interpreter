# Meeting Interpreter

A real-time bidirectional meeting interpreter built with [LiveKit Agents](https://docs.livekit.io/agents/) (Python) and a Next.js (TypeScript) web client. A room runs one **language pair** — Bengali ⇄ English (`bn-en`), Bengali ⇄ Japanese (`bn-ja`) or English ⇄ Japanese (`en-ja`). For each remote participant, the agent creates a dedicated translation session that hears their speech in their selected language and publishes translated audio into the room under `translated-<target>`; SFU-level track subscription permissions ensure each participant only receives translations into their selected language.


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
uv run pytest -q        # 105 tests
uv run ruff check .

# Local development worker
uv run python -m agent.main dev

# Production worker (LiveKit Cloud agent deployment)
uv run python -m agent.main start
```

`agent/main.py` loads config (failing fast with variable *names* only), registers an `AgentServer` whose `agent_name` comes from `AGENT_NAME` (default `meeting-interpreter`), resolves the room's language pair from the dispatch/room metadata, and for each room creates an `InterpreterManager` that spawns one `AgentSession` per remote participant based on their `language` attribute. Sessions restart when that attribute changes and are closed on disconnect.

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

Join with an identity, choose a language pair and your language, then press **Start speaking (unmute)** to publish your microphone - the agent can only translate audio from participants who are unmuted. For the chosen pair, a participant receives translations into the partner language (`translated-<target>` tracks):

- **Bengali ⇄ English** (`bn-en`): English speakers receive `translated-bn`, Bengali speakers receive `translated-en`
- **Bengali ⇄ Japanese** (`bn-ja`): Bengali speakers receive `translated-ja`, Japanese speakers receive `translated-bn`
- **English ⇄ Japanese** (`en-ja`): English speakers receive `translated-ja`, Japanese speakers receive `translated-en`


## Configuration

Agent variables (`.env.example`, parsed by `agent/config.py`):

| Variable | Default | Notes |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | — | required; missing names are reported, values never are |
| `STT_MODEL` | `deepgram/nova-3` | LiveKit Inference model ID |
| `LLM_MODEL` | `openai/gpt-4o-mini` | LiveKit Inference model ID |
| `TTS_MODEL` | `cartesia/sonic-3` | LiveKit Inference model ID |
| `TTS_VOICE_BN` | `314be1d2-3d14-468d-be40-08a1af7df49d` | Cartesia voice for Bengali output |
| `TTS_VOICE_EN` | `47c38ca4-5f35-497b-b1a3-415245fb35e1` | Cartesia voice for English output |
| `TTS_VOICE_JA` | `aa3ccc4a-cfd8-405c-acf5-1873a527b006` | Cartesia voice for Japanese output ("Yuzuki") |
| `LANGUAGE_PAIR` | `bn-en` | default room pair (`bn-en`, `bn-ja` or `en-ja`); a join request can override it |
| `AGENT_NAME` | `meeting-interpreter` | worker registration / dispatch name |
| `TOKEN_TTL_SECONDS` | `3600` | must be a positive integer |

Web variables (`web/.env.example`):

- `NEXT_PUBLIC_LIVEKIT_URL` (client-visible room URL; also used by the token route when `LIVEKIT_URL` is unset)
- `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (server-side token generation only)
- `LIVEKIT_ROOM_NAME` (optional, default `interpreter-room`) - the shared meeting room
- `AGENT_NAME` (optional, default `meeting-interpreter`) - must match the agent's `AGENT_NAME`
- `LANGUAGE_PAIR` (optional, default `bn-en`) - default pair when a join request omits one
- `TOKEN_TTL_SECONDS` (optional, default `3600`)

The join request sends the selected pair; the token endpoint stamps it into the token attributes, the dispatch metadata and `roomConfig.metadata`, and the agent reads it to run one pair per room. Joining an existing room with a conflicting pair is rejected.

The web client must point at the **same LiveKit project** as the agent, otherwise the dispatch lands in a project with no registered worker and no translation session starts.

## Testing

```bash
uv run pytest -q      # tests/test_config.py, test_routing.py, test_prompts.py
uv run ruff check .   # line length 100, rules: E, F, I, W, UP, B (web/ and docs/ excluded)

cd web && npm run build   # compiles the Next.js client and type-checks /api/token
```

