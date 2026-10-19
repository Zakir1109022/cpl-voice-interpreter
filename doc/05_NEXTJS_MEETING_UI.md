# Task 05 — Next.js Meeting UI

## Goal

Build a minimal, usable web interface to create/join a LiveKit meeting and select each participant's language.

## UI requirements

- Create/join meeting controls.
- Language selector with Bengali (`bn`) and English (`en`).
- Microphone mute/unmute.
- Connection status and agent status.
- Optional source and translated captions.
- Clear indication that translated voice is AI-generated.
- Safe error messages for unavailable models, disconnected participants and exhausted inference allowance.

## Security requirements

- Obtain a short-lived LiveKit access token from a backend endpoint.
- Never expose `LIVEKIT_API_SECRET` or other server credentials in browser code.
- Validate room and participant inputs server-side.
- Follow the existing repository's Next.js conventions and package manager.
- Do not add unrelated UI libraries unless the project requires them.

## Integration requirements

- Connect to LiveKit using the supported client SDK.
- Register the participant's selected source language using the application's defined signaling/API mechanism.
- Display session/agent status from the supported backend/agent event mechanism.
- If captions are implemented, show source and translated text distinctly and associate them with the appropriate participant/direction.
- Ensure mute state and disconnect/reconnect UI match the actual LiveKit connection state.

## Deliverables

- Meeting page/components.
- Room create/join and token integration.
- Language selection and microphone controls.
- Connection/agent/error status UI.
- Setup instructions for the web application.

## Acceptance checks

- A participant can join a room and choose `bn` or `en`.
- The browser never receives server credentials.
- Connection and error states are understandable.
- The UI does not imply translation is working when the agent/model is unavailable.
