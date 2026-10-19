"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useIsSpeaking,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
} from "@livekit/components-react";
import { ConnectionState, ParticipantKind, RoomEvent } from "livekit-client";
import type { Participant, RemoteParticipant } from "livekit-client";

const STATUS_TOPIC = "interpreter-status";

type Language = "bn" | "en";
type StatusTone = "success" | "warning" | "error" | "info";

type InterpreterStatus = {
  type: string;
  message?: string;
  stage?: string;
  source_language?: Language;
  target_language?: Language;
};

const LANGUAGE_INFO: Record<Language, { code: string; name: string; native: string }> = {
  en: { code: "EN", name: "English", native: "English" },
  bn: { code: "BN", name: "Bengali", native: "বাংলা" },
};

const STATUS_PRESENTATION: Record<string, { title: string; tone: StatusTone }> = {
  session_ready: { title: "Interpreter active", tone: "success" },
  language_error: { title: "Language needed", tone: "warning" },
  session_start_error: { title: "Interpreter could not start", tone: "error" },
  pipeline_error: { title: "Interpretation problem", tone: "error" },
};

function isLanguage(value: unknown): value is Language {
  return value === "bn" || value === "en";
}

function languageOf(participant: Participant): Language | null {
  const value = participant.attributes?.language;
  return isLanguage(value) ? value : null;
}

function targetOf(language: Language): Language {
  return language === "en" ? "bn" : "en";
}

function displayNameOf(participant: Participant): string {
  const raw = (participant.name || participant.identity || "").trim();
  if (!raw) return "Participant";
  return raw.replace(/^agent-/, "AI ").replace(/[_-]+/g, " ");
}

function initialsOf(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function connectionPresentation(state: ConnectionState): { label: string; tone: string } {
  switch (state) {
    case ConnectionState.Connected:
      return { label: "Connected", tone: "ok" };
    case ConnectionState.Connecting:
    case ConnectionState.Reconnecting:
    case ConnectionState.SignalReconnecting:
      return { label: "Connecting…", tone: "warn" };
    default:
      return { label: "Disconnected", tone: "off" };
  }
}

function IconMic({ off = false }: { off?: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3.75a2.5 2.5 0 0 0-2.5 2.5v5a2.5 2.5 0 0 0 5 0v-5a2.5 2.5 0 0 0-2.5-2.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M5.5 11.25v.5a6.5 6.5 0 0 0 13 0v-.5M12 18.25v2.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {off && (
        <path
          d="M4.5 4.5l15 15"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

function IconSpark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconBot() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4.5" y="8" width="15" height="11" rx="3.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 8V4.8M12 4.8a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4Z" stroke="currentColor" strokeWidth="1.5" />
      <path d="M9.5 13v1.6M14.5 13v1.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="m8.6 12.3 2.3 2.3 4.5-4.9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconWarning() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4.6 20 19H4l8-14.4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M12 10v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="12" cy="16.6" r="0.9" fill="currentColor" />
    </svg>
  );
}

function IconInfo() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 11v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="12" cy="8.2" r="0.95" fill="currentColor" />
    </svg>
  );
}

function statusIcon(tone: StatusTone) {
  if (tone === "success") return <IconCheck />;
  if (tone === "error") return <IconWarning />;
  if (tone === "warning") return <IconWarning />;
  return <IconInfo />;
}

function useInterpreterStatus() {
  const room = useRoomContext();
  const [status, setStatus] = useState<InterpreterStatus | null>(null);

  useEffect(() => {
    if (!room) return;
    const handleData = (
      payload: Uint8Array,
      participant?: RemoteParticipant,
      _kind?: unknown,
      topic?: string,
    ) => {
      if (topic && topic !== STATUS_TOPIC) return;
      if (participant?.identity === room.localParticipant.identity) return;
      try {
        const parsed = JSON.parse(new TextDecoder().decode(payload));
        if (parsed && typeof parsed === "object" && typeof parsed.type === "string") {
          setStatus(parsed as InterpreterStatus);
        }
      } catch {
        return;
      }
    };
    room.on(RoomEvent.DataReceived, handleData);
    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room]);

  return status;
}

function ParticipantRow({ participant, isLocal }: { participant: Participant; isLocal: boolean }) {
  const speaking = useIsSpeaking(participant);
  const isAgent = participant.kind === ParticipantKind.AGENT;
  const language = languageOf(participant);
  const name = displayNameOf(participant);
  const micOn = participant.isMicrophoneEnabled;
  const avatarVariant = isAgent ? "ai" : (language ?? "unknown");

  const subtitle = isAgent
    ? "Bengali ⇄ English interpreter"
    : language
      ? isLocal
        ? `You speak ${LANGUAGE_INFO[language].name} · you hear ${LANGUAGE_INFO[targetOf(language)].name}`
        : `Hears ${LANGUAGE_INFO[targetOf(language)].name}`
      : "Waiting for a language selection";

  return (
    <li className={`participant${speaking ? " participant--speaking" : ""}`}>
      <span className={`avatar avatar--${avatarVariant}${speaking ? " avatar--speaking" : ""}`}>
        {isAgent ? <IconBot /> : initialsOf(name)}
      </span>
      <div className="participant-body">
        <div className="participant-line">
          <span className="participant-name">{name}</span>
          {isLocal && <span className="chip chip--you">You</span>}
          {isAgent && <span className="chip chip--agent">AI</span>}
          {!isAgent && language && (
            <span className={`chip chip--${language}`}>
              {LANGUAGE_INFO[language].code} · {LANGUAGE_INFO[language].native}
            </span>
          )}
          {!isAgent && !language && <span className="chip chip--warn">No language</span>}
        </div>
        <div className="participant-sub">{subtitle}</div>
      </div>
      <div className="participant-meta">
        {speaking && (
          <span className="speak-bars" role="img" aria-label={`${name} is speaking`}>
            <span />
            <span />
            <span />
          </span>
        )}
        {!isAgent && (
          <span className={`mic-state${micOn ? "" : " mic-state--off"}`}>
            <IconMic off={!micOn} />
            <span className="sr-only">{micOn ? "Microphone on" : "Microphone muted"}</span>
          </span>
        )}
      </div>
    </li>
  );
}

function RoomContent() {
  const room = useRoomContext();
  const participants = useParticipants();
  const local = useLocalParticipant();
  const connectionState = useConnectionState();
  const status = useInterpreterStatus();
  const [micBusy, setMicBusy] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const localIdentity = local.localParticipant.identity;
  const micOn = local.isMicrophoneEnabled;
  const connection = connectionPresentation(connectionState);

  const ordered = useMemo(() => {
    const rank = (participant: Participant) => {
      if (participant.identity === localIdentity) return 0;
      return participant.kind === ParticipantKind.AGENT ? 1 : 2;
    };
    return [...participants].sort((a, b) => {
      const delta = rank(a) - rank(b);
      return delta !== 0 ? delta : displayNameOf(a).localeCompare(displayNameOf(b));
    });
  }, [participants, localIdentity]);

  const others = ordered.filter((participant) => participant.identity !== localIdentity);
  const presentation = status
    ? STATUS_PRESENTATION[status.type] ?? { title: status.type, tone: "info" as StatusTone }
    : null;

  const statusDetail =
    status?.type === "session_ready" && status.source_language && status.target_language
      ? `You speak ${LANGUAGE_INFO[status.source_language].name} and hear ${LANGUAGE_INFO[status.target_language].name}.`
      : status?.message;

  const toggleMicrophone = async () => {
    setMicBusy(true);
    setMicError(null);
    try {
      await local.localParticipant.setMicrophoneEnabled(!micOn);
    } catch (err) {
      setMicError(
        err instanceof Error && err.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow it in your browser and try again."
          : "Could not start the microphone.",
      );
    } finally {
      setMicBusy(false);
    }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <IconSpark />
          </span>
          <div>
            <h1 className="brand-title">Meeting Interpreter</h1>
            <p className="brand-sub">Live Bengali ⇄ English interpretation</p>
          </div>
        </div>
        <div className="topbar-meta">
          {room?.name && <span className="pill">{room.name}</span>}
          <span className={`pill pill--${connection.tone}`}>
            <span className="dot" />
            {connection.label}
          </span>
        </div>
      </header>

      <section className="card">
        <div className="card-head">
          <h2 className="section-label">Participants</h2>
          <span className="counter">
            {ordered.length} {ordered.length === 1 ? "person" : "people"}
          </span>
        </div>
        <ul className="participants">
          {ordered.map((participant) => (
            <ParticipantRow
              key={participant.identity}
              participant={participant}
              isLocal={participant.identity === localIdentity}
            />
          ))}
        </ul>
        {others.length === 0 && (
          <p className="hint" style={{ marginTop: "12px" }}>
            You are the only person here. Share the room name so others can join.
          </p>
        )}
      </section>

      {presentation && status && (
        <div className={`status status--${presentation.tone}`} role="status" aria-live="polite">
          <span className="status-icon" aria-hidden="true">
            {statusIcon(presentation.tone)}
          </span>
          <div className="status-body">
            <div className="status-title">
              {presentation.title}
              {status.source_language && status.target_language && (
                <>
                  <span className={`chip chip--${status.source_language}`}>
                    {LANGUAGE_INFO[status.source_language].code}
                  </span>
                  <span aria-hidden="true">→</span>
                  <span className={`chip chip--${status.target_language}`}>
                    {LANGUAGE_INFO[status.target_language].code}
                  </span>
                </>
              )}
            </div>
            {statusDetail && <p className="status-text">{statusDetail}</p>}
            {status.type === "pipeline_error" && status.stage && (
              <p className="status-raw">stage: {status.stage}</p>
            )}
          </div>
        </div>
      )}

      <section className="card">
        <div className="mic-row">
          <div className="mic-copy">
            <p className="mic-title">Your microphone</p>
            <p className="mic-hint">
              {micOn
                ? "Live — your speech is being interpreted for the other participants."
                : "Muted. Unmute to let others hear and be interpreted."}
            </p>
          </div>
          <button
            type="button"
            className={`btn ${micOn ? "btn--danger" : "btn--primary"}`}
            onClick={toggleMicrophone}
            disabled={micBusy || connectionState !== ConnectionState.Connected}
            aria-pressed={micOn}
          >
            <IconMic off={!micOn} />
            {micBusy ? "Please wait…" : micOn ? "Mute microphone" : "Start speaking"}
          </button>
        </div>
        {micError && <p className="error-text">{micError}</p>}
      </section>

      <div className="shell-footer">
        <span>Translated voices you hear are AI-generated.</span>
        <span>Signed in as {displayNameOf(local.localParticipant)}</span>
      </div>

      <RoomAudioRenderer />
    </div>
  );
}

export default function Home() {
  const [identity, setIdentity] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [token, setToken] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const identityInput = useRef<HTMLInputElement>(null);

  const livekitUrl = useMemo(() => {
    if (url) return url;
    return process.env.NEXT_PUBLIC_LIVEKIT_URL || "";
  }, [url]);

  const fetchToken = async () => {
    const entered = (identityInput.current?.value ?? identity).trim();
    if (!entered) {
      setError("Enter an identity to join.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identity: entered, language }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Token request failed (${res.status})`);
      }
      const data = await res.json();
      setToken(data.token);
      if (data.url) setUrl(data.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch token");
    } finally {
      setLoading(false);
    }
  };

  if (token && livekitUrl) {
    return (
      <main>
        <LiveKitRoom
          token={token}
          serverUrl={livekitUrl}
          connect={true}
          data-lk-theme="default"
          style={{ width: "100%" }}
        >
          <RoomContent />
        </LiveKitRoom>
      </main>
    );
  }

  return (
    <main>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void fetchToken();
        }}
        className="card"
        style={{ display: "flex", flexDirection: "column", gap: "1rem", width: "min(420px, 100%)" }}
      >
        <h1 className="brand-title" style={{ margin: 0 }}>
          Join Meeting
        </h1>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <span className="section-label">Identity</span>
          <input
            ref={identityInput}
            value={identity}
            onChange={(e) => setIdentity(e.target.value)}
            placeholder="e.g. alice"
            className="input"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <span className="section-label">Your language</span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as Language)}
            className="input"
          >
            <option value="en">English (will receive Bengali translation)</option>
            <option value="bn">Bengali (will receive English translation)</option>
          </select>
        </label>
        <button type="submit" className="btn btn--primary" disabled={loading} style={{ justifyContent: "center" }}>
          {loading ? "Joining…" : "Join Room"}
        </button>
        {error && <p className="error-text" style={{ margin: 0 }}>{error}</p>}
      </form>
    </main>
  );
}
