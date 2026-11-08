// The calls: SIP over the websocket of the server to its Asterisk, which takes them to VoIP.ms. A websocket cannot
// carry a header, so the API key goes in the URL of the websocket, and the server checks it before Caddy opens it.
import * as JsSIP from "jssip";
import type { RTCSession } from "jssip/lib/RTCSession";
import type { RTCSessionEvent } from "jssip/lib/UA";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, SERVER_KEY, SERVER_URL } from "./api";

// The device finds its public address here. Asterisk has a public address of its own, so no relay is needed.
const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];
const AUDIO = { audio: true, video: false };
const HOST = new URL(SERVER_URL).host;

export type CallState = {
  number: string;
  incoming: boolean;
  status: "calling" | "ringing" | "incoming" | "connecting" | "active" | "ended";
  muted: boolean;
  early?: boolean;
  startedAt: number | null;
};

// ---------------------------------------------------------------- tones

let context: AudioContext | undefined;

// A web view plays sound only after a tap. Each tap calls this, so the ring of a call that comes in later can play.
export function unlockAudio() {
  try {
    context ??= new AudioContext();
    if (context.state === "suspended") void context.resume();
  } catch {
    // No Web Audio: the calls still work, without the tones.
  }
}

// Play FREQUENCIES in the rhythm of STEPS (seconds on, seconds off, ...) for two minutes, or until the returned
// function stops it.
function tone(frequencies: number[], steps: number[], volume: number) {
  const ctx = context;
  if (!ctx) return () => {};
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);
  const oscillators = frequencies.map((frequency) => {
    const oscillator = ctx.createOscillator();
    oscillator.frequency.value = frequency;
    oscillator.connect(gain);
    oscillator.start();
    return oscillator;
  });
  const cycle = steps.reduce((a, b) => a + b, 0);
  let at = ctx.currentTime;
  for (let n = 0; n < 120 / cycle; n++) {
    steps.forEach((step, i) => {
      gain.gain.setValueAtTime(i % 2 ? 0 : volume, at);
      at += step;
    });
  }
  return () => {
    oscillators.forEach((oscillator) => oscillator.stop());
    gain.disconnect();
  };
}

// The North American ringback, and a double ring for a call that comes in.
const ringback = () => tone([440, 480], [2, 4], 0.08);
const ringtone = () => tone([440, 480], [0.4, 0.2, 0.4, 2], 0.25);

// ---------------------------------------------------------------- the phone

// The SIP agent and the one call it can have. AUDIO_REF is the <audio> element that plays the other side.
export function useCalls(audioRef: React.RefObject<HTMLAudioElement | null>) {
  const agent = useRef<JsSIP.UA | null>(null);
  const session = useRef<RTCSession | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [call, setCall] = useState<CallState | null>(null);
  // The own numbers, from the server. The list of numbers shows them before the first sync of the texts ends.
  const [dids, setDids] = useState<string[]>([]);
  const [locked, setLocked] = useState<string[]>([]);

  const follow = useCallback(
    (s: RTCSession, first: Pick<CallState, "number" | "incoming" | "status">) => {
      session.current = s;
      setCall({ muted: false, startedAt: null, ...first });
      const play = (pc: RTCPeerConnection) =>
        pc.addEventListener("track", (e) => {
          const audio = audioRef.current;
          if (!audio) return;
          audio.srcObject = e.streams[0];
          audio.play().catch(() => {});
        });
      if (s.connection) play(s.connection);
      s.on("peerconnection", (e) => play(e.peerconnection));
      // JsSIP waits for every ICE candidate before it sends the offer or the answer. One from the STUN server is
      // enough, and it comes in a moment.
      s.on("icecandidate", (e) => {
        if (e.candidate.type === "srflx") e.ready();
      });
      s.on("progress", (e: { response?: { body?: string } }) => {
        if (first.incoming) return;
        // With a body the carrier sends its own ringing, as early media.
        const early = Boolean(e.response?.body);
        setCall((c) => c && { ...c, status: "ringing", early });
      });
      const start = () => setCall((c) => c && { ...c, status: "active", startedAt: c.startedAt || Date.now() });
      s.on("accepted", start);
      s.on("confirmed", start);
      const end = (e: { cause?: string }) => {
        if (session.current === s) session.current = null;
        if (e?.cause === JsSIP.C.causes.USER_DENIED_MEDIA_ACCESS) setError("Allow the microphone to call.");
        setCall((c) => c && { ...c, status: "ended" });
        setTimeout(() => setCall((c) => (c?.status === "ended" ? null : c)), 1500);
      };
      s.on("ended", end);
      s.on("failed", end);
    },
    [audioRef],
  );

  useEffect(() => {
    let stopped = false;
    (async () => {
      let account;
      try {
        account = await api.account();
      } catch (e) {
        setError(String((e as Error).message || e));
        return;
      }
      if (stopped) return;
      setDids(account.dids);
      setLocked(account.locked ?? []);
      if (!account.password) return;
      const ua = new JsSIP.UA({
        sockets: [new JsSIP.WebSocketInterface(`wss://${HOST}/phone/ws?key=${encodeURIComponent(SERVER_KEY)}`)],
        uri: `sip:${account.user}@${HOST}`,
        password: account.password,
        register: true,
        register_expires: 300,
        session_timers: false,
        user_agent: "lines",
        connection_recovery_min_interval: 2,
        connection_recovery_max_interval: 30,
      });
      ua.on("registered", () => {
        setReady(true);
        setError("");
      });
      ua.on("unregistered", () => setReady(false));
      ua.on("registrationFailed", () => setReady(false));
      ua.on("disconnected", () => setReady(false));
      ua.on("newRTCSession", ({ session: s, originator, request }: RTCSessionEvent) => {
        if (originator !== "remote") return;
        // One call at a time: a second caller hears busy.
        if (session.current) {
          s.terminate({ status_code: 486, reason_phrase: "Busy Here" });
          return;
        }
        follow(s, { number: request.from.uri.user, incoming: true, status: "incoming" });
      });
      ua.start();
      agent.current = ua;
    })();
    return () => {
      stopped = true;
      agent.current?.stop();
      agent.current = null;
    };
  }, [follow]);

  // The ring of a call that comes in, and the ringback of one going out until the carrier sends its own.
  useEffect(() => {
    if (call?.status === "incoming") return ringtone();
    if (call?.status === "ringing" && !call.early) return ringback();
  }, [call?.status, call?.early]);

  // FROM is the own number that Asterisk puts on the call as its caller ID. VoIP.ms refuses a call without one.
  const dial = useCallback(
    (number: string, from: string) => {
      unlockAudio();
      if (session.current) return;
      if (!agent.current?.isRegistered()) {
        setError("The phone is offline.");
        return;
      }
      const s = agent.current.call(`sip:${number}@${HOST}`, {
        mediaConstraints: AUDIO,
        pcConfig: { iceServers: ICE_SERVERS },
        extraHeaders: [`X-Caller: ${from}`],
      });
      follow(s, { number, incoming: false, status: "calling" });
    },
    [follow],
  );

  const answer = useCallback(() => {
    unlockAudio();
    session.current?.answer({ mediaConstraints: AUDIO, pcConfig: { iceServers: ICE_SERVERS } });
    setCall((c) => c && { ...c, status: "connecting" });
  }, []);

  // Decline answers busy, so VoIP.ms takes the caller to voicemail.
  const hangup = useCallback(() => {
    const s = session.current;
    if (!s) return;
    if (s.direction === "incoming" && !s.isEstablished()) s.terminate({ status_code: 486, reason_phrase: "Busy Here" });
    else s.terminate();
  }, []);

  const mute = useCallback(() => {
    const s = session.current;
    if (!s) return;
    const muted = !s.isMuted().audio;
    if (muted) s.mute({ audio: true });
    else s.unmute({ audio: true });
    setCall((c) => c && { ...c, muted });
  }, []);

  const dtmf = useCallback((key: string) => {
    session.current?.sendDTMF(key, { transportType: JsSIP.C.DTMF_TRANSPORT.RFC2833 });
  }, []);

  return { ready, error, call, dids, locked, dial, answer, hangup, mute, dtmf };
}
