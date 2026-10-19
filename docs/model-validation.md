# Model Validation — Bengali ↔ English Meeting Interpreter

Verified against official LiveKit documentation on **2026-10-19**. All models below are accessed through **LiveKit Inference** (billed to the LiveKit Cloud project; no separate provider API keys required).

## Selected pipeline (go)

| Stage | Provider | Model ID | Bengali (`bn`) | English (`en`) | Evidence |
|---|---|---|---|---|---|
| STT | Deepgram | `deepgram/nova-3` | yes (`bn` listed) | yes (`en` listed) | [Deepgram STT model table](https://docs.livekit.io/agents/models/stt/deepgram/#inference) |
| Translation LLM | OpenAI | `openai/gpt-4o-mini` | yes | yes | [LLM models list](https://docs.livekit.io/agents/models/llm/#inference); strong multilingual translation, low latency/cost |
| TTS | Cartesia | `cartesia/sonic-3` | yes (`bn` listed) | yes (`en` listed) | [Cartesia TTS model table](https://docs.livekit.io/agents/models/tts/cartesia/#inference) |

**Conclusion: GO.** Both directions (`bn → en` and `en → bn`) have a viable STT → LLM → TTS path through LiveKit Inference with a single LiveKit Cloud project.

## Rejected / fallback candidates

| Candidate | Result | Reason |
|---|---|---|
| Deepgram Flux (`deepgram/flux-general-multi`) | Rejected for this build | Multilingual model does not list `bn` (covers `en, es, fr, de, hi, ru, pt, ja, it, nl`) |
| Deepgram TTS (`deepgram/aura-2`) | Rejected | No Bengali support (no `bn` in language list) |
| Cartesia `cartesia/sonic-3.5` / `sonic-3.6` | Fallback | Also list `bn` + `en`; usable if `sonic-3` quality for Bengali is unsatisfactory. `sonic-2` is deprecated (retires 2026-10-20) |
| Inworld TTS | Not selected | Candidate from source plan; Cartesia via Inference already covers both languages with one provider, so Inworld was not needed |
| Google/Soniox/Gladia STT | Not selected | Soniox/Gladia offer built-in translation but require their own plugin API keys; Deepgram Nova-3 via Inference covers both languages with one provider |

## Required packages

Python (see `pyproject.toml`):

- `livekit-agents[openai]~=1.8` — agent framework, `inference` module (Deepgram STT, Cartesia TTS, OpenAI LLM all served by LiveKit Inference; the `openai` extra is only needed if you switch `LLM_MODEL` to an OpenAI plugin ID — the default uses Inference and needs no provider key)
- `livekit-api` — server-side token minting for tests/tooling
- `python-dotenv`

The frontend uses `livekit-server-sdk` (Node) for token minting and agent dispatch.

## Pricing / quota caveats (LiveKit Inference, Build plan as of 2026-10-19)

- Build plan includes **$2.50 inference credits (~50 agent minutes)** and **5 concurrent inference requests**; concurrent STT/LLM/TTS usage is per-session-model, so a two-participant meeting consumes roughly double the per-minute model cost of a single voice agent (two STT streams, two TTS streams, two LLM streams while both parties speak).
- `deepgram/nova-3`: $0.0048/min (monolingual) or $0.0058/min (multilingual) — this app pins monolingual per participant, so the monolingual rate applies.
- `cartesia/sonic-3`: $50 per 1M characters.
- `openai/gpt-4o-mini`: $0.15 per 1M input tokens, $0.60 per 1M output tokens.
- Agent session hosting on LiveKit Cloud: $0.01/min per running agent session, plus WebRTC participant minutes.
- Credits are consumed in real time; when exhausted, Inference calls fail with quota errors. The agent surfaces these as non-fatal per-participant errors (see README troubleshooting). **No free-usage claims are made beyond the plan credits listed above.**

## Account setup required

1. A LiveKit Cloud project (Build plan is sufficient for development) with Inference enabled.
2. No Deepgram/Cartesia/OpenAI keys needed when using the default model IDs via LiveKit Inference.

## Unresolved items (do not block implementation)

- Bengali voice naturalness for `cartesia/sonic-3` requires a manual listening check (voice IDs are configurable via `TTS_VOICE_BN` / `TTS_VOICE_EN`).
- Default voices are copied verbatim from the [Cartesia voice library](https://docs.livekit.io/agents/models/tts/cartesia/#voices): `9626c31c-bec5-4cca-baa8-f8ba9e84c8bc` (`en`, Jacqueline) and `f786b574-daa5-4673-aa0c-cbe3e8534c02` (`bn`). An inexact voice ID makes the provider return no audio, which `AgentSession` reports as `LiveKit Inference TTS returned error: ... "TTS provider completed without producing audio"`. Verified by synthesis on 2026-10-19: `sonic-3` produces Bengali audio for both `language="bn"` and unset language with that voice, and also for the `en` voice with `language="bn"`.
- Latency targets must be validated in the manual end-to-end test; correctness is prioritized first per the task plan.
