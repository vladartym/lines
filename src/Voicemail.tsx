// The voicemail box, from the server (server/phone/voicemail.py). A tap opens a message: it plays, shows the transcript when
// VoIP.ms made one, and can be marked as read or deleted. A delete is for good, so it takes a second tap.
// The audio of each message stays on the device (store.ts), so a message plays at once, also with no network.
import { useEffect, useState } from "react";
import { api, type Voicemail as Message } from "./api";
import { duration, listTime, pretty } from "./format";
import { forgetAudio, keepAudio, keptAudio, keptAudioKeys } from "./store";

// VoIP.ms numbers the messages again after a delete, so the audio goes by the date and the caller.
const audioKey = (m: Message) => `${m.date} ${m.number}`;

// A data URL of MP3. VoIP.ms sometimes sends no audio, and the server once sent "base64,False": such a value is never
// kept, and one that was kept before is fetched again.
const MP3 = "data:audio/mpeg;base64,";
function sound(s: string | undefined): s is string {
  try {
    return !!s && s.startsWith(MP3) && atob(s.slice(MP3.length)).length > 0;
  } catch {
    return false; // Not base64, such as "False".
  }
}

// The MP3 of a message: from the device when it is there, else from the server, and then kept. VoIP.ms sends no audio
// about one time in two, and the server asks it twice, so the app asks the server up to 3 times.
async function audioOf(m: Message): Promise<string> {
  const known = await keptAudio(audioKey(m));
  if (sound(known)) return known;
  for (let tries = 1; ; tries++) {
    try {
      const { audio } = await api.voicemailAudio(m);
      if (!sound(audio)) throw new Error("VoIP.ms sent no audio for that message. Try again.");
      await keepAudio(audioKey(m), audio);
      return audio;
    } catch (e) {
      if (tries === 3) throw e;
    }
  }
}

// After each load of the list: keep the audio of each new message, and forget the audio of the messages that are
// gone. One message at a time, because VoIP.ms limits its API.
let fetching = false;
export async function keepAllAudio(messages: Message[]) {
  if (fetching) return;
  fetching = true;
  try {
    const keys = messages.map(audioKey);
    const known = await keptAudioKeys();
    for (const key of known) if (!keys.includes(key)) await forgetAudio(key);
    for (const m of messages) await audioOf(m).catch(() => {});
  } finally {
    fetching = false;
  }
}

const RATE = 8000;

// iOS cannot play the MP3 of VoIP.ms (MPEG 2.5 at 8 kHz) in an audio element: it loads for ever. Web Audio decodes
// it, so the player gets it as WAV.
async function playable(mp3: string): Promise<string> {
  const bytes = Uint8Array.from(atob(mp3.slice(mp3.indexOf(",") + 1)), (c) => c.charCodeAt(0));
  const pcm = (await new OfflineAudioContext(1, 1, RATE).decodeAudioData(bytes.buffer)).getChannelData(0);
  const wav = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const text = (at: number, s: string) => [...s].forEach((c, i) => wav.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF");
  wav.setUint32(4, 36 + pcm.length * 2, true);
  text(8, "WAVEfmt ");
  wav.setUint32(16, 16, true);
  wav.setUint16(20, 1, true); // PCM
  wav.setUint16(22, 1, true); // mono
  wav.setUint32(24, RATE, true);
  wav.setUint32(28, RATE * 2, true);
  wav.setUint16(32, 2, true);
  wav.setUint16(34, 16, true);
  text(36, "data");
  wav.setUint32(40, pcm.length * 2, true);
  pcm.forEach((v, i) => wav.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return URL.createObjectURL(new Blob([wav], { type: "audio/wav" }));
}

export function Voicemail({ messages, names, lineNames, onChange, onReload, onError }: {
  messages: Message[] | null;
  names: Map<string, string>;
  lineNames: Record<string, string>;
  onChange: (messages: Message[]) => void;
  onReload: () => void;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState("");
  if (!messages) return <p className="empty">Loading</p>;
  if (!messages.length) return <p className="empty">No voicemail</p>;

  const id = (m: Message) => `${m.folder}/${m.num}/${m.date}`;
  // The server refuses a message that VoIP.ms numbered again, so each refusal reloads the list.
  const failed = (e: Error) => {
    onError(e.message);
    onReload();
  };
  const read = (m: Message) => {
    onChange(messages.map((x) => (id(x) === id(m) ? { ...x, listened: true } : x)));
    api.markRead(m).catch(failed);
  };
  // VoIP.ms numbers the other messages again after a delete, so the list loads again.
  const remove = (m: Message) => {
    onChange(messages.filter((x) => id(x) !== id(m)));
    setOpen("");
    api.deleteVoicemail(m).then(onReload, failed);
  };

  return (
    <ul className="list">
      {messages.map((m) => (
        <Row key={id(m)} message={m} name={names.get(m.number) || pretty(m.number) || "No Caller ID"}
          called={m.called && (lineNames[m.called] || pretty(m.called))} open={open === id(m)}
          onToggle={() => setOpen(open === id(m) ? "" : id(m))} onRead={() => read(m)} onDelete={() => remove(m)}
          onError={onError} />
      ))}
    </ul>
  );
}

function Row({ message: m, name, called, open, onToggle, onRead, onDelete, onError }: {
  message: Message;
  name: string;
  called: string;
  open: boolean;
  onToggle: () => void;
  onRead: () => void;
  onDelete: () => void;
  onError: (message: string) => void;
}) {
  const [audio, setAudio] = useState("");
  const [failed, setFailed] = useState(false);
  const [sure, setSure] = useState(false);
  useEffect(() => {
    if (open && !audio) {
      setFailed(false);
      audioOf(m).then(playable).then(setAudio, (e) => {
        setFailed(true);
        onError(e.message);
      });
    }
    if (!open) setSure(false);
  }, [open]);
  useEffect(() => () => URL.revokeObjectURL(audio), [audio]);

  return (
    <li className="row voicemail" onClick={onToggle}>
      <span className={m.listened ? "dot off" : "dot"} />
      <div className="row-main">
        <div className="row-top">
          <b>{name}</b>
          <span className="muted small">{listTime(m.at)}</span>
        </div>
        <div className="row-top muted small">
          <span>{called}</span>
          <span>{duration(m.seconds)}</span>
        </div>
        {open && (
          <div className="message" onClick={(e) => e.stopPropagation()}>
            {m.transcript && <p>{m.transcript}</p>}
            {audio ? <audio controls src={audio} onPlay={() => !m.listened && onRead()} />
              : !failed && <p className="muted small">Loading</p>}
            <div className="message-actions">
              {!m.listened ? <button className="link" onClick={onRead}>Mark as Read</button> : <span />}
              <button className="danger" onClick={() => (sure ? onDelete() : setSure(true))}>
                {sure ? "Delete for Good" : "Delete"}
              </button>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}
