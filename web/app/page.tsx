"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
} from "@livekit/components-react";
import { RoomEvent } from "livekit-client";
import type { RemoteParticipant } from "livekit-client";

const STATUS_TOPIC = "interpreter-status";

type Language = "bn" | "en";

function useInterpreterStatus() {
  const room = useRoomContext();
  const local = useLocalParticipant();
  const [status, setStatus] = useState<{
    type: string;
    message?: string;
    source_language?: Language;
    target_language?: Language;
  } | null>(null);

  useEffect(() => {
    if (!room) return;
    const handleData = (payload: Uint8Array, participant?: RemoteParticipant) => {
      if (participant?.identity !== room.localParticipant.identity) return;
      try {
        const text = new TextDecoder().decode(payload);
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object") {
          setStatus(parsed as any);
        }
      } catch (err) {
        console.warn("failed to parse interpreter status", err);
      }
    };
    room.on(RoomEvent.DataReceived, handleData);
    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room, local.localParticipant.identity]);

  return status;
}

function RoomContent() {
  const participants = useParticipants();
  const local = useLocalParticipant();
  const status = useInterpreterStatus();
  const [micBusy, setMicBusy] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const others = participants.filter((p) => p.identity !== local.localParticipant.identity);
  const micOn = local.isMicrophoneEnabled;

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
    <section style={{ display: "flex", flexDirection: "column", gap: "1rem", width: "min(720px, 100%)" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Bengali &lt;-&gt; English Interpreter</h1>
        <span style={{ fontSize: "0.875rem", opacity: 0.8 }}>Participants: {participants.length}</span>
      </header>
      <div style={{ background: "rgba(255,255,255,0.05)", borderRadius: "0.75rem", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div>
          <strong>Your identity:</strong> {local.localParticipant.identity || "(joining...)"}
        </div>
        <div>
          <strong>Your language attribute:</strong> {local.localParticipant.attributes.language || "(not set)"}
        </div>
        <div>
          <strong>Other participants:</strong> {others.length === 0 ? "None" : others.map((p) => p.identity).join(", ")}
        </div>
        {status && (
          <div style={{ marginTop: "0.25rem" }}>
            <strong>Status [{status.type}]:</strong> {status.message || JSON.stringify(status)}
          </div>
        )}
      </div>
      <div style={{ background: "rgba(255,255,255,0.05)", borderRadius: "0.75rem", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button
            onClick={toggleMicrophone}
            disabled={micBusy}
            style={{
              padding: "0.75rem 1rem",
              borderRadius: "0.5rem",
              border: "none",
              background: micOn ? "#b91c1c" : "#16a34a",
              color: "white",
              fontWeight: 600,
              cursor: micBusy ? "not-allowed" : "pointer",
            }}
          >
            {micBusy ? "Please wait..." : micOn ? "Mute microphone" : "Start speaking (unmute)"}
          </button>
          <span style={{ fontSize: "0.875rem", opacity: 0.85 }}>
            Microphone: {micOn ? "on - others hear your voice" : "off"}
          </span>
        </div>
        {micError && <div style={{ color: "#f87171" }}>{micError}</div>}
        <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>
          Translated voices you hear are AI-generated.
        </div>
      </div>
      <RoomAudioRenderer />
    </section>
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
        style={{ display: "flex", flexDirection: "column", gap: "1rem", width: "min(420px, 100%)", background: "rgba(255,255,255,0.05)", padding: "1.5rem", borderRadius: "0.75rem" }}
      >
        <h1 style={{ margin: 0 }}>Join Meeting</h1>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <span>Identity</span>
          <input
            ref={identityInput}
            value={identity}
            onChange={(e) => setIdentity(e.target.value)}
            placeholder="e.g. alice"
            style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "1px solid rgba(255,255,255,0.3)", background: "transparent", color: "inherit" }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <span>Your language</span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as Language)}
            style={{ padding: "0.5rem", borderRadius: "0.5rem", border: "1px solid rgba(255,255,255,0.3)", background: "transparent", color: "inherit" }}
          >
            <option value="en">English (will receive Bengali translation)</option>
            <option value="bn">Bengali (will receive English translation)</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "0.75rem", borderRadius: "0.5rem", border: "none", background: "#4f46e5", color: "white", fontWeight: 600, cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "Joining..." : "Join Room"}
        </button>
        {error && <div style={{ color: "#f87171" }}>{error}</div>}
      </form>
    </main>
  );
}
