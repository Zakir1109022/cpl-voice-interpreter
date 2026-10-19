# Task 01 — Validate LiveKit Inference Models Before Coding the Pipeline

## Goal

Verify that available LiveKit Inference options support the languages needed for both directions before implementing audio processing.

## Requirements

1. Inspect the current LiveKit Inference catalog and official documentation.
2. Identify supported choices for:
   - STT: Bengali audio → Bengali transcript (`bn`).
   - STT: English audio → English transcript (`en`).
   - Translation LLM: Bengali ↔ English text.
   - TTS: English text → English audio (`en`).
   - TTS: Bengali text → Bengali audio (`bn`).
3. Confirm the current SDK/plugin installation instructions for each selected model.
4. Check whether the chosen models are available to the intended LiveKit account and document any usage limits/pricing relevant to development.
5. Keep the model names configurable; avoid binding application logic to one provider.
6. If a language/model combination is unavailable, stop and report the blocker rather than pretending it works.

## Candidate models

The source plan mentions Deepgram Nova-3 as an STT candidate and Cartesia or Inworld as TTS candidates. Treat these only as candidates: confirm current Bengali/English language support and availability before selecting them. Do not assume the candidates support both languages.

## Deliverables

- A short `docs/model-validation.md` documenting:
  - Selected model/provider and model identifier for each stage.
  - Bengali and English support evidence.
  - Required packages/plugins and versions or install instructions.
  - Any account setup or billing/quota caveats.
  - Unsupported combinations and fallback decisions, if applicable.
- Update `.env.example` with configurable model identifiers after validating them.
- A clear go/no-go conclusion for implementation.

## Acceptance checks

- Both language directions have a viable STT → LLM translation → TTS path.
- The exact current SDK APIs and plugin names are sourced from official documentation.
- No claim of free usage or model availability is made without evidence.

## Official references

- https://docs.livekit.io/agents/
- https://docs.livekit.io/agents/models/inference/
- https://docs.livekit.io/agents/models/stt/
- https://docs.livekit.io/agents/models/tts/
- https://livekit.com/pricing/inference
