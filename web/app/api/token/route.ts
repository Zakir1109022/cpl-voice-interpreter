import {
  AccessToken,
  AgentDispatchClient,
  RoomAgentDispatch,
  RoomConfiguration,
} from "livekit-server-sdk";
import { NextResponse } from "next/server";

const DEFAULT_ROOM_NAME = "interpreter-room";
const DEFAULT_AGENT_NAME = "bengali-english-interpreter";
const DEFAULT_TOKEN_TTL_SECONDS = 3600;

const SUPPORTED_LANGUAGES = ["bn", "en"];

// LiveKit identities and room names are user-supplied, so keep them to a
// conservative character set rather than forwarding arbitrary strings.
const IDENTITY_PATTERN = /^[A-Za-z0-9._@-]{1,128}$/;
const ROOM_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function errorResponse(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

/** The server SDK talks to the Room/Agent APIs over HTTP(S), not websockets. */
function toHttpUrl(livekitUrl: string): string {
  if (livekitUrl.startsWith("wss://")) return `https://${livekitUrl.slice("wss://".length)}`;
  if (livekitUrl.startsWith("ws://")) return `http://${livekitUrl.slice("ws://".length)}`;
  return livekitUrl;
}

function tokenTtlSeconds(): number {
  const parsed = Number.parseInt((process.env.TOKEN_TTL_SECONDS ?? "").trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_TOKEN_TTL_SECONDS;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Creates a token for one participant and makes sure the interpreter agent is
 * dispatched to the room.
 *
 * Dispatch is deduplicated two ways: the token carries a `roomConfig.agents`
 * entry (applied atomically when LiveKit creates the room) and an explicit
 * dispatch is created only when none is recorded for this agent name. Two jobs
 * in one room would each publish translated audio, so a second dispatch must
 * never be created for a room that already has one.
 */
export async function POST(request: Request) {
  const apiKey = asString(process.env.LIVEKIT_API_KEY);
  const apiSecret = asString(process.env.LIVEKIT_API_SECRET);
  const livekitUrl = asString(process.env.LIVEKIT_URL || process.env.NEXT_PUBLIC_LIVEKIT_URL);
  const agentName = asString(process.env.AGENT_NAME) || DEFAULT_AGENT_NAME;

  const missing = [
    ["LIVEKIT_API_KEY", apiKey],
    ["LIVEKIT_API_SECRET", apiSecret],
    ["LIVEKIT_URL", livekitUrl],
  ]
    .filter(([, value]) => !value)
    .map(([name]) => name);
  if (missing.length > 0) {
    console.error(`[api/token] missing server configuration: ${missing.join(", ")}`);
    return errorResponse("Server is not configured for token generation", 500);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse("Request body must be valid JSON", 400);
  }

  const payload = (body ?? {}) as Record<string, unknown>;
  const identity = asString(payload.identity);
  const language = asString(payload.language);
  const room = asString(payload.room) || asString(process.env.LIVEKIT_ROOM_NAME) || DEFAULT_ROOM_NAME;

  if (!IDENTITY_PATTERN.test(identity)) {
    return errorResponse(
      "identity must be 1-128 characters using letters, digits, '_', '.', '@' or '-'",
      400,
    );
  }
  if (!SUPPORTED_LANGUAGES.includes(language)) {
    return errorResponse(`language must be one of: ${SUPPORTED_LANGUAGES.join(", ")}`, 400);
  }
  if (!ROOM_PATTERN.test(room)) {
    return errorResponse("room must be 1-64 characters using letters, digits, '_' or '-'", 400);
  }

  try {
    const httpUrl = toHttpUrl(livekitUrl);

    // listDispatch fails when the room does not exist yet, in which case the
    // token's roomConfig dispatches the agent as the room is created
    const dispatchClient = new AgentDispatchClient(httpUrl, apiKey, apiSecret);
    const dispatches = await dispatchClient.listDispatch(room).catch(() => null);
    if (dispatches !== null && !dispatches.some((d) => d.agentName === agentName)) {
      await dispatchClient.createDispatch(room, agentName);
    }

    const token = new AccessToken(apiKey, apiSecret, {
      identity,
      name: identity,
      ttl: tokenTtlSeconds(),
      attributes: { language },
    });
    token.addGrant({
      roomJoin: true,
      room,
      canSubscribe: true,
      canPublish: true,
      canPublishData: true,
    });
    token.roomConfig = new RoomConfiguration({
      agents: [new RoomAgentDispatch({ agentName })],
    });

    return NextResponse.json({ token: await token.toJwt(), url: livekitUrl });
  } catch (error) {
    // server-side detail stays in the server logs; the client gets a generic message
    console.error(`[api/token] failed to create a token for room '${room}'`, error);
    return errorResponse("Failed to create a join token", 500);
  }
}
