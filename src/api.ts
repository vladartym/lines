// The Lines server (server/): it holds the VoIP.ms API key, copies the texts in, and runs Asterisk for the calls. A
// device cannot call the VoIP.ms API itself, because VoIP.ms takes only the addresses on its list.
// The fetch of the HTTP plugin goes from Rust, so the server needs no CORS for this app.
import { fetch } from "@tauri-apps/plugin-http";

export const SERVER_URL = import.meta.env.VITE_SERVER_URL;
export const SERVER_KEY = import.meta.env.VITE_SERVER_KEY;

export type Thread = { did: string; contact: string; body: string; media: number; incoming: boolean; at: string; unread: number };
export type Text = { id: number; incoming: boolean; body: string; media: string[]; at: string };
export type Call = { id: string; at: string; incoming: boolean; number: string; answered: boolean; seconds: number };
// locked: optional, the numbers that the server marks as locked. The list shows a lock on each.
export type Account = { user: string; password: string; dids: string[]; locked?: string[] };
export type Settings = { forward_to: string; forward_on: boolean };
// FOLDER, NUM and DATE name the message for an action: VoIP.ms numbers the messages again after a delete.
export type Voicemail = {
  folder: string; num: number; date: string; at: string; number: string; called: string; seconds: number;
  listened: boolean; transcript: string;
};

const message = (m: Voicemail) => new URLSearchParams({ folder: m.folder, num: String(m.num), date: m.date });

// In a browser (bun run dev) there is no Tauri, so the page goes through the proxy of vite.config.ts.
const inApp = "__TAURI_INTERNALS__" in window;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await (inApp ? fetch : window.fetch)(`${inApp ? SERVER_URL : "/server"}/api/v1${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${SERVER_KEY}`, "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().then((b) => b.detail, () => "");
    throw new Error(detail || `The server answered ${response.status}`);
  }
  return response.json();
}

export const api = {
  account: () => call<Account>("/phone"),
  // With sync, the server first copies in the texts of the last 90 days from VoIP.ms.
  threads: (sync = false) => call<{ dids: string[] | null; threads: Thread[] }>(`/texts/threads${sync ? "?sync=true" : ""}`),
  thread: (did: string, contact: string) =>
    call<{ texts: Text[] }>(`/texts/thread?did=${encodeURIComponent(did)}&contact=${encodeURIComponent(contact)}`),
  // MEDIA is a picture as a data URL, and the text then goes as MMS.
  send: (did: string, to: string, body: string, media = "") =>
    call<{ contact: string; texts: Text[] }>("/texts", { method: "POST", body: JSON.stringify({ did, to, body, media }) }),
  calls: () => call<{ calls: Call[] }>("/calls"),
  voicemail: () => call<{ messages: Voicemail[] }>("/voicemail"),
  // The message as a data URL of MP3, which the audio element plays as it is.
  voicemailAudio: (m: Voicemail) => call<{ audio: string }>(`/voicemail/audio?${message(m)}`),
  markRead: (m: Voicemail) =>
    call<{ ok: boolean }>("/voicemail/read", { method: "PUT", body: JSON.stringify({ folder: m.folder, num: m.num, date: m.date }) }),
  deleteVoicemail: (m: Voicemail) => call<{ ok: boolean }>(`/voicemail?${message(m)}`, { method: "DELETE" }),
  settings: () => call<Settings>("/phone/settings"),
  saveSettings: (s: Settings) => call<Settings>("/phone/settings", { method: "PUT", body: JSON.stringify(s) }),
  // The names that the user gave the numbers, by number. An empty name takes one off.
  lineNames: () => call<{ names: Record<string, string> }>("/phone/names"),
  saveLineName: (did: string, name: string) =>
    call<{ names: Record<string, string> }>("/phone/names", { method: "PUT", body: JSON.stringify({ did, name }) }),
  // The APNs token of the iPhone, so the server can push texts and calls to it.
  addDevice: (token: string) => call<{ ok: boolean }>("/phone/devices", { method: "POST", body: JSON.stringify({ token }) }),
};
