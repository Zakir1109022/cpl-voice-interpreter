# Web client (Next.js + LiveKit)

This Next.js App Router client connects to the LiveKit room created by the Python agent worker. The UI lets a participant choose their language (`bn` or `en`), requests a token from `/api/token` with that language in attributes, joins the room, and only subscribes to translated audio tracks for their selected language.

## Setup

1. Install dependencies
```bash
cd web
npm install
```

2. Configure environment
```bash
cp .env.example .env.local
```
Set:
- `NEXT_PUBLIC_LIVEKIT_URL` (e.g. `wss://your-project.livekit.cloud`)
- `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` (server-side for token generation)

Optional:
- `LIVEKIT_ROOM_NAME` - shared meeting room, default `interpreter-room`
- `AGENT_NAME` - worker to dispatch, default `meeting-interpreter` (must match the Python agent)
- `TOKEN_TTL_SECONDS` - token lifetime, default `3600`

The credentials must belong to the same LiveKit project the Python agent worker runs against.

3. Run dev server
```bash
npm run dev
```

Check the client compiles and type-checks with:
```bash
npm run build
```

## How it works
- Token endpoint (`app/api/token/route.ts`) validates `identity` (1-128 chars of `A-Za-z0-9._@-`), `language` (`bn|en`) and `room` (1-64 chars of `A-Za-z0-9_-`, default `LIVEKIT_ROOM_NAME` / `interpreter-room`), creates an AccessToken with `attributes = { language }`, grants room join + subscribe/publish/data, dispatches the `AGENT_NAME` worker (unless the room already has a dispatch for it), and returns `{ token, url }`. Server credentials are only read from server-side env vars and errors are returned as generic messages.
- Room page (`app/page.tsx`) subscribes to the LiveKit room and uses `RoomAudioRenderer`. After joining it shows your identity, language and the agent's status, and provides a **Start speaking / Mute microphone** button (`setMicrophoneEnabled`) so your audio is published to the room; the agent only hears participants who turned their mic on. Microphone permission errors are surfaced next to the button, and translated audio is labelled as AI-generated. It listens to `interpreter-status` data messages addressed to the local identity (topic `interpreter-status`). The agent publishes status messages when sessions start, language is missing/invalid, or pipeline errors occur.
- Audio routing: each agent session publishes translated audio under `translated-<target>` (e.g. Bengali speaker -> `translated-en`). The SFU restricts each participant's subscriptions so they only receive tracks whose target matches their selected `language` attribute. The UI does not need to manually filter tracks; LiveKit's subscription permissions enforce this.
