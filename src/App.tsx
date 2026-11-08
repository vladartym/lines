// Lines: texts and calls from the VoIP.ms numbers. The number at the top is the line that texts and calls go out
// from, and the line whose texts the list shows.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Call, type Thread, type Voicemail as Message } from "./api";
import { digits, duration, pretty } from "./format";
import { Icon, type IconName } from "./icons";
import { Keys } from "./Keypad";
import { Conversation, ThreadList } from "./Messages";
import { type Contact, loadContacts, namesOf, nativeTabs, pushToken } from "./native";
import { type CallState, unlockAudio, useCalls } from "./phone";
import { Pick } from "./Pick";
import { Recents } from "./Recents";
import { Settings } from "./Settings";
import { keep, kept } from "./store";
import { keepAllAudio, Voicemail } from "./Voicemail";

type Tab = "messages" | "calls" | "keypad" | "voicemail";
type View = null | { thread: string } | { pick: "text" | "call" } | { numbers: true } | { settings: true; from?: "numbers" };

const TABS: [Tab, string, IconName][] = [
  ["messages", "Messages", "messages"],
  ["calls", "Calls", "phone"],
  ["keypad", "Keypad", "keypad"],
  ["voicemail", "Voicemail", "voicemail"],
];

declare global {
  interface Window {
    linesTab?: (tab: Tab) => void;
    linesNative?: (kind: "line" | "action" | "settings" | "numbers", value: string) => void;
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>("messages");
  const [view, setView] = useState<View>(null);
  // Each list starts from what the device kept (store.ts), and the server then brings it up to date.
  const [lines, setLines] = useState<string[]>(() => kept("lines") ?? []);
  const [from, setFrom] = useState(() => localStorage.getItem("lines.from") || "");
  const [threads, setThreads] = useState<Thread[]>(() => kept("threads") ?? []);
  const [calls, setCalls] = useState<Call[] | null>(() => kept("calls"));
  const [voicemail, setVoicemail] = useState<Message[] | null>(() => kept("voicemail"));
  const [contacts, setContacts] = useState<Contact[]>([]);
  // The names of the numbers, such as "Work", from the server, so the Mac and the iPhone show the same.
  const [lineNames, setLineNames] = useState<Record<string, string>>(() => kept("lineNames") ?? {});
  const [error, setError] = useState("");
  const [nativeBar, setNativeBar] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);
  const phone = useCalls(audio);
  const names = useMemo(() => namesOf(contacts), [contacts]);
  useEffect(() => {
    if (phone.dids.length) setLines(phone.dids);
  }, [phone.dids]);
  const line = lines.includes(from) ? from : lines[0] || "";
  useEffect(() => keep("lines", lines), [lines]);
  useEffect(() => keep("threads", threads), [threads]);
  useEffect(() => void (calls && keep("calls", calls)), [calls]);
  useEffect(() => void (voicemail && keep("voicemail", voicemail)), [voicemail]);
  useEffect(() => keep("lineNames", lineNames), [lineNames]);

  const loadThreads = useCallback((sync = false) => {
    api.threads(sync).then(
      (r) => {
        if (r.dids) setLines(r.dids);
        setThreads(r.threads);
        setError("");
      },
      (e) => setError(e.message),
    );
  }, []);

  // The list shows the copy on the server at once, and again when the first sync has copied the new texts in from
  // VoIP.ms, which takes some seconds. Then it reads the copy every few seconds.
  useEffect(() => {
    loadThreads();
    loadThreads(true);
    const timer = setInterval(() => loadThreads(), 8000);
    loadContacts().then(setContacts);
    api.lineNames().then((r) => setLineNames(r.names), () => {});
    // The iPhone gives the server its token at each start, so the pushes of texts and calls come to Lines.
    pushToken().then((token) => {
      if (token) void api.addDevice(token).catch(() => {});
    });
    return () => clearInterval(timer);
  }, [loadThreads]);

  const loadCalls = useCallback(() => {
    api.calls().then((r) => setCalls(r.calls), (e) => setError(e.message));
  }, []);
  // Each open of the tab reads VoIP.ms through the server, and nothing reads it in between: VoIP.ms limits its API.
  const loadVoicemail = useCallback(() => {
    api.voicemail().then((r) => {
      setVoicemail(r.messages);
      void keepAllAudio(r.messages);
    }, (e) => setError(e.message));
  }, []);
  // The voicemail also loads at the start, so the audio of a new message is on the device before it opens.
  useEffect(loadVoicemail, [loadVoicemail]);
  useEffect(() => {
    if (tab === "calls") loadCalls();
    if (tab === "voicemail") loadVoicemail();
  }, [tab, loadCalls, loadVoicemail]);

  const choose = (did: string) => {
    localStorage.setItem("lines.from", did);
    setFrom(did);
  };

  const unread = (did: string) => threads.filter((t) => t.did === did).reduce((n, t) => n + t.unread, 0);

  // The native tab bar in Liquid Glass on iOS 26 and macOS 26, else the bar of the page. On the Mac the menu of the
  // lines and the button at the top right are native too. They hide in a conversation, a pick and a call.
  const covered = Boolean(view || phone.call);
  const action = tab === "messages" ? "compose" : tab === "calls" ? "contact" : "";
  const nativeState = JSON.stringify({
    tab, hidden: covered, line, action,
    lines: lines.map((did) => ({ did, title: lineNames[did] ? `${lineNames[did]} · ${pretty(did)}` : pretty(did), unread: unread(did) })),
  });
  window.linesTab = (t) => {
    setView(null);
    setTab(t);
  };
  window.linesNative = (kind, value) => {
    if (kind === "line") choose(value);
    else if (kind === "settings") setView({ settings: true });
    else if (kind === "numbers") setView({ numbers: true });
    else setView({ pick: tab === "messages" ? "text" : "call" });
  };
  useEffect(() => {
    nativeTabs(JSON.parse(nativeState)).then(setNativeBar);
  }, [nativeState]);
  const nativeTop = nativeBar && document.documentElement.classList.contains("mac");

  // The name of a number, else the number.
  const label = (did: string) => lineNames[did] || pretty(did);

  // The screen shows the new name at once. A refusal puts back the names of the server.
  const nameLine = (did: string, name: string) => {
    const next = { ...lineNames };
    if (name.trim()) next[did] = name.trim();
    else delete next[did];
    setLineNames(next);
    api.saveLineName(did, name).then((r) => setLineNames(r.names), (e) => {
      setError(e.message);
      api.lineNames().then((r) => setLineNames(r.names), () => {});
    });
  };

  const dial = (number: string) => {
    if (line) phone.dial(number, line);
  };

  const shown = threads.filter((t) => t.did === line);

  let page;
  if (view && "thread" in view) {
    page = (
      <Conversation did={line} contact={view.thread} name={names.get(view.thread)} onBack={() => setView(null)}
        onCall={() => dial(view.thread)} onSent={() => loadThreads()} />
    );
  } else if (view && "numbers" in view) {
    page = (
      <Numbers lines={lines} line={line} names={lineNames} locked={phone.locked} unread={unread} onName={nameLine} onBack={() => setView(null)}
        onChoose={(did) => {
          choose(did);
          setView(null);
        }}
        onSettings={() => setView({ settings: true, from: "numbers" })} />
    );
  } else if (view && "settings" in view) {
    page = <Settings onBack={() => setView(view.from ? { numbers: true } : null)} />;
  } else if (view && "pick" in view) {
    const call = view.pick === "call";
    page = (
      <Pick title={call ? "New Call" : "New Message"} contacts={contacts} onCancel={() => setView(null)}
        onPick={(number) => {
          if (call) {
            setView(null);
            dial(number);
          } else setView({ thread: number });
        }} />
    );
  } else {
    page = (
      <div className="page">
        <header className="bar">
          {!nativeTop && (
            <button className="line" onClick={() => setView({ numbers: true })}>
              {line ? label(line) : "…"} <Icon name="down" size={14} />
            </button>
          )}
          <span />
          {!nativeTop && tab === "messages" && (
            <button className="icon end" onClick={() => setView({ pick: "text" })} aria-label="New message">
              <Icon name="compose" />
            </button>
          )}
          {!nativeTop && tab === "calls" && (
            <button className="icon end" onClick={() => setView({ pick: "call" })} aria-label="New call">
              <Icon name="person" />
            </button>
          )}
        </header>
        <h1>{TABS.find(([t]) => t === tab)?.[1]}</h1>
        {error && <p className="error">{error}</p>}
        <div className="scroll">
          {tab === "messages" && <ThreadList threads={shown} names={names} onOpen={(contact) => setView({ thread: contact })} />}
          {tab === "calls" && <Recents calls={calls} names={names} onCall={dial} />}
          {tab === "keypad" && <Dialer onDial={dial} onContacts={() => setView({ pick: "call" })} />}
          {tab === "voicemail" && (
            <Voicemail messages={voicemail} names={names} lineNames={lineNames} onChange={setVoicemail}
              onReload={loadVoicemail} onError={setError} />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={nativeBar ? "app native-bar" : "app"} onPointerDown={unlockAudio}>
      <div className="drag" data-tauri-drag-region />
      {page}
      {!nativeBar && !covered && (
        <nav className="tabs">
          {TABS.map(([t, title, icon]) => (
            <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>
              <Icon name={icon} />
              <span>{title}</span>
            </button>
          ))}
        </nav>
      )}
      {!phone.ready && !phone.call && <p className="offline">{phone.error || "Connecting"}</p>}
      {phone.call && (
        <CallScreen call={phone.call} name={names.get(phone.call.number)} line={label(line)} onAnswer={phone.answer}
          onHangup={() => {
            phone.hangup();
            if (tab === "calls") setTimeout(loadCalls, 3000);
          }}
          onMute={phone.mute} onKey={phone.dtmf} />
      )}
      <audio ref={audio} autoPlay />
    </div>
  );
}

function Dialer({ onDial, onContacts }: { onDial: (number: string) => void; onContacts: () => void }) {
  const [number, setNumber] = useState("");
  return (
    <div className="dialer">
      <div className="typed">{number ? pretty(number) : " "}</div>
      <Keys onKey={(k) => setNumber((n) => (n + k).slice(0, 15))} />
      <div className="dial-row">
        <button className="icon round" onClick={onContacts} aria-label="Contacts"><Icon name="person" /></button>
        <button className="call-button" disabled={number.length < 3} onClick={() => onDial(number)} aria-label="Call">
          <Icon name="phone" size={30} />
        </button>
        <button className="icon round" disabled={!number} onClick={() => setNumber((n) => n.slice(0, -1))} aria-label="Delete">
          <Icon name="erase" />
        </button>
      </div>
    </div>
  );
}

function CallScreen({ call, name, line, onAnswer, onHangup, onMute, onKey }: {
  call: CallState;
  name?: string;
  line: string;
  onAnswer: () => void;
  onHangup: () => void;
  onMute: () => void;
  onKey: (key: string) => void;
}) {
  const [keys, setKeys] = useState(false);
  const [pressed, setPressed] = useState("");
  const [, tick] = useState(0);
  useEffect(() => {
    if (call.status !== "active") return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [call.status]);

  const status = {
    calling: "Calling…",
    ringing: "Ringing…",
    incoming: `Incoming call to ${line}`,
    connecting: "Connecting…",
    active: duration((Date.now() - (call.startedAt || Date.now())) / 1000),
    ended: "Call ended",
  }[call.status];

  return (
    <div className="call">
      <div className="who">
        <h2>{name || pretty(call.number)}</h2>
        <p>{keys && pressed ? pressed : status}</p>
      </div>
      {keys && <Keys onKey={(k) => {
        onKey(k);
        setPressed((p) => p + k);
      }} />}
      {call.status === "incoming" ? (
        <div className="call-actions">
          <button className="end-button" onClick={onHangup} aria-label="Decline"><Icon name="phone" size={30} /></button>
          <button className="call-button" onClick={onAnswer} aria-label="Answer"><Icon name="phone" size={30} /></button>
        </div>
      ) : (
        <div className="call-actions">
          <button className={call.muted ? "icon round on" : "icon round"} onClick={onMute} aria-label="Mute">
            <Icon name="mute" />
          </button>
          <button className="end-button" onClick={onHangup} disabled={call.status === "ended"} aria-label="End">
            <Icon name="phone" size={30} />
          </button>
          <button className={keys ? "icon round on" : "icon round"} onClick={() => setKeys((k) => !k)} aria-label="Keypad">
            <Icon name="keypad" />
          </button>
        </div>
      )}
    </div>
  );
}

// The numbers of the account, as a page of its own: a tap makes one the line that texts and calls go out from. A
// search finds a number by its digits or its name, and Edit gives each number a name.
function Numbers({ lines, line, names, locked, unread, onBack, onChoose, onSettings, onName }: {
  lines: string[];
  line: string;
  names: Record<string, string>;
  locked: string[];
  unread: (did: string) => number;
  onBack: () => void;
  onChoose: (did: string) => void;
  onSettings: () => void;
  onName: (did: string, name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);
  const words = query.trim().toLowerCase();
  const typed = digits(query);
  const shown = lines.filter((did) => !words || (names[did] ?? "").toLowerCase().includes(words) || (typed && did.includes(typed)));

  return (
    <div className="page">
      <header className="bar">
        <button className="icon bar-side" onClick={onBack} aria-label="Back"><Icon name="back" /></button>
        <h2>Numbers</h2>
        <button className="link bar-side end" onClick={() => setEditing((e) => !e)}>{editing ? "Done" : "Edit"}</button>
      </header>
      <div className="scroll settings">
        <label className="search">
          <Icon name="search" size={17} />
          <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)}
            autoCorrect="off" autoCapitalize="off" />
        </label>
        <p className="section">Your numbers</p>
        <div className="group">
          {shown.map((did) =>
            editing ? (
              <div key={did} className="cell">
                <div className="cell-two">
                  <input className="name" placeholder="Add a name" defaultValue={names[did] ?? ""} maxLength={40}
                    onBlur={(e) => e.target.value.trim() !== (names[did] ?? "") && onName(did, e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
                  <small>{pretty(did)}</small>
                </div>
              </div>
            ) : (
              <button key={did} className="cell" onClick={() => onChoose(did)}>
                <div className="cell-two">
                  {/* A locked number, as the server marks it. */}
                  <span className="locked-name">{names[did] || pretty(did)}
                    {locked.includes(did) && <span className="lock" aria-label="Locked"><Icon name="lock" size={15} /></span>}</span>
                  {names[did] && <small>{pretty(did)}</small>}
                </div>
                <span className="cell-end">
                  {unread(did) > 0 && <span className="count">{unread(did)}</span>}
                  {did === line && <Icon name="check" />}
                </span>
              </button>
            ),
          )}
          {!shown.length && <p className="cell muted">No numbers</p>}
        </div>
        <div className="group apart">
          <button className="cell" onClick={onSettings}>
            <span>Settings</span>
            <span className="cell-end muted"><Icon name="next" size={18} /></span>
          </button>
        </div>
      </div>
    </div>
  );
}
