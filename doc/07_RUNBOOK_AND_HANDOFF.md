# Task 07 — Runbook, Documentation and Handoff

## Goal

Make the implementation reproducible for another developer or coding agent.

## Required documentation

Update the repository `README.md` with:

1. Project purpose and supported directions (Bengali ↔ English).
2. Architecture summary.
3. Prerequisites.
4. Python environment setup.
5. Next.js setup.
6. LiveKit Cloud project and credential setup.
7. Model configuration, based on the verified choices in `docs/model-validation.md`.
8. `.env` configuration instructions.
9. Commands to run tests, linting and type checks.
10. Commands to start the Python agent and Next.js UI.
11. Manual two-participant end-to-end test steps.
12. Troubleshooting for missing environment variables, unsupported models/languages, connection errors and inference quota exhaustion.
13. Known limitations and current cost/free-usage caveats, without claiming free usage unless verified.

## Operational requirements

- Ensure `.env` is ignored by Git and `.env.example` contains placeholders only.
- Explain how to rotate exposed credentials if they were accidentally committed.
- Document logs and metrics while emphasizing that raw audio is not stored by default.
- Explain how to verify that the selected STT/TTS models still support Bengali and English.
- Do not document commands that were not tested or verified.

## Final acceptance checklist

- [ ] Fresh setup instructions are complete.
- [ ] Python agent starts using the documented command.
- [ ] Next.js UI starts using the documented command.
- [ ] Both language directions pass the end-to-end test.
- [ ] Automated tests and available lint/type checks pass.
- [ ] Credentials are not exposed to the frontend or committed.
- [ ] Model compatibility and cost caveats are documented.
- [ ] Known limitations are listed honestly.

## Final handoff response

Provide:
- Architecture and implementation summary.
- Commands to run backend/agent and frontend.
- Test results.
- Environment variables that must be supplied by the developer (names only, never values).
- Any remaining blockers or limitations.
