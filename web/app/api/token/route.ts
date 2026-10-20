import {
  AccessToken,
  AgentDispatchClient,
  RoomAgentDispatch,
  RoomConfiguration,
} from "livekit-server-sdk";
import { NextResponse } from "next/server";

const DEFAULT_ROOM_NAME = "interpreter-room";
const DEFAULT_AGENT_NAME = "meeting-interpreter";
const DEFAULT_TOKEN_TTL_SECONDS = 3600;

// Each room runs exactly one language pair; a participant picks one language from
// the pair and hears the other. Keep the canonical order (bn < en < ja) so that
// "ja-bn" and "bn-ja" are treated as the same pair.
const LANGUAGE_PAIRS: Record<string, readonly string[]> = {
  "bn-en": ["bn", "en"],
  "bn-ja": ["bn", "ja"],
  "en-ja": ["en", "ja"],
};
const DEFAULT_PAIR = "bn-en";

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

/** Canonicalize a pair code ("JA-BN", "bn_ja", "bn, ja" -> "bn-ja"), or "" if unknown. */
function normalizePair(value: string): string {
  const parts = value
    .toLowerCase()
    .replace(/[_,]/g, "-")
    .split("-")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (parts.length !== 2 || parts[0] === parts[1]) return "";
  const code = [`${parts[0]}-${parts[1]}`, `${parts[1]}-${parts[0]}`].find(
    (candidate) => candidate in LANGUAGE_PAIRS,
  );
  return code ?? "";
}

function pairMetadata(pair: string): string {
  return JSON.stringify({ pair });
}

/** Recover a canonical pair from dispatch/room metadata, or "" when absent. */
function pairFromMetadata(metadata: string | undefined): string {
  if (!metadata) return "";
  const raw = metadata.trim();
  if (!raw) return "";
  if (raw.startsWith("{")) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && "pair" in parsed) {
        return normalizePair(asString((parsed as { pair?: unknown }).pair));
      }
    } catch {
      return "";
    }
    return "";
  }
  return normalizePair(raw);
}

/**
 * Creates a token for one participant and makes sure the interpreter agent is
 * dispatched to the room.
 *
 * The room's language pair flows to the agent through two channels: the token's
 * `roomConfig.metadata` (applied atomically when LiveKit creates the room) and,
 * for rooms that already exist, the dispatch metadata. Because one room runs one
 * pair, a join that requests a conflicting pair is rejected instead of silently
 * mis-translating.
 *
 * Dispatch is deduplicated two ways: the token carries a `roomConfig.agents`
 * entry and an explicit dispatch is created only when none is recorded for this
 * agent name. Two jobs in one room would each publish translated audio, so a
 * second dispatch must never be created for a room that already has one.
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
  const language = asString(payload.language).toLowerCase();
  const room = asString(payload.room) || asString(process.env.LIVEKIT_ROOM_NAME) || DEFAULT_ROOM_NAME;

  // Voice cloning consent (join-screen checkbox). Only an explicit opt-in stamps
  // "true"; the agent never enrolls a participant without it.
  const voiceConsent = payload.voiceConsent === true || payload.voiceConsent === "true";

  const requestedPair = asString(payload.pair)
    ? normalizePair(asString(payload.pair))
    : asString(process.env.LANGUAGE_PAIR)
      ? normalizePair(asString(process.env.LANGUAGE_PAIR))
      : DEFAULT_PAIR;
  const pair = requestedPair || "";
  if (!pair) {
    return errorResponse(
      `pair must be one of: ${Object.keys(LANGUAGE_PAIRS).join(", ")}`,
      400,
    );
  }
  const pairLanguages = LANGUAGE_PAIRS[pair];

  if (!IDENTITY_PATTERN.test(identity)) {
    return errorResponse(
      "identity must be 1-128 characters using letters, digits, '_', '.', '@' or '-'",
      400,
    );
  }
  if (!pairLanguages.includes(language)) {
    return errorResponse(`language must be one of: ${pairLanguages.join(", ")}`, 400);
  }
  if (!ROOM_PATTERN.test(room)) {
    return errorResponse("room must be 1-64 characters using letters, digits, '_' or '-'", 400);
  }

  try {
    const httpUrl = toHttpUrl(livekitUrl);
    const metadata = pairMetadata(pair);

    // listDispatch fails when the room does not exist yet, in which case the
    // token's roomConfig dispatches the agent as the room is created
    const dispatchClient = new AgentDispatchClient(httpUrl, apiKey, apiSecret);
    const dispatches = await dispatchClient.listDispatch(room).catch(() => null);
    const existing = dispatches?.find((d) => d.agentName === agentName);
    if (existing) {
      const existingPair = pairFromMetadata(existing.metadata);
      if (existingPair && existingPair !== pair) {
        return errorResponse(
          `Room '${room}' is already set to language pair '${existingPair}'`,
          409,
        );
      }
    } else if (dispatches !== null) {
      await dispatchClient.createDispatch(room, agentName, { metadata });
    }

    const token = new AccessToken(apiKey, apiSecret, {
      identity,
      name: identity,
      ttl: tokenTtlSeconds(),
      attributes: { language, pair, voice_cloning_consent: voiceConsent ? "true" : "false" },
    });
    token.addGrant({
      roomJoin: true,
      room,
      canSubscribe: true,
      canPublish: true,
      canPublishData: true,
    });
    token.roomConfig = new RoomConfiguration({
      metadata,
      agents: [new RoomAgentDispatch({ agentName, metadata })],
    });

    return NextResponse.json({ token: await token.toJwt(), url: livekitUrl });
  } catch (error) {
    // server-side detail stays in the server logs; the client gets a generic message
    console.error(`[api/token] failed to create a token for room '${room}'`, error);
    return errorResponse("Failed to create a join token", 500);
  }
}
