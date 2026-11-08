// The texts of the selected number: the list of conversations, and one conversation.
import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, type Text, type Thread } from "./api";
import { keep, kept } from "./store";
import { listTime, pretty, stampTime } from "./format";
import { Icon } from "./icons";

export function ThreadList({ threads, names, onOpen }: {
  threads: Thread[];
  names: Map<string, string>;
  onOpen: (contact: string) => void;
}) {
  if (!threads.length) return <p className="empty">No messages</p>;
  return (
    <ul className="list">
      {threads.map((t) => (
        <li key={t.contact} className="row" onClick={() => onOpen(t.contact)}>
          <span className={t.unread ? "dot" : "dot off"} />
          <div className="row-main">
            <div className="row-top">
              <b>{names.get(t.contact) || pretty(t.contact)}</b>
              <span className="muted small">{listTime(t.at)}</span>
            </div>
            <span className="muted clamp">{t.body || (t.media ? "Attachment" : "")}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// A new stamp over a text that comes more than an hour after the one before it, as in Messages.
const GAP = 3600000;

// A text that shows at once when it goes out, until the HQ answers with the conversation.
type Outgoing = { key: number; body: string; media?: string; at: string; failed?: boolean };
// One bubble: a text from the HQ, or one that goes out now.
type Row = { key: string; incoming: boolean; body: string; media: string[]; at: string; out?: Outgoing };

const apart = (a: Row, b: Row) => new Date(b.at).getTime() - new Date(a.at).getTime() > GAP;

// A picture from the camera or the library, as a JPEG data URL that VoIP.ms takes: at most 1600 px on its long side,
// and under about 1.2 MB, the limit for one picture in an MMS.
async function shrink(file: File): Promise<string> {
  const image = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(image.width * scale);
  canvas.height = Math.round(image.height * scale);
  canvas.getContext("2d")!.drawImage(image, 0, 0, canvas.width, canvas.height);
  for (const quality of [0.8, 0.6, 0.45]) {
    const url = canvas.toDataURL("image/jpeg", quality);
    if (url.length < 1_600_000) return url;
  }
  return canvas.toDataURL("image/jpeg", 0.3);
}

// "JD" for Jane Doe, the first letter of a one-word name.
function initials(name?: string) {
  return (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

// One conversation in the look of Messages on iOS 26 and 27: the contact in the middle of a glass top, bubbles with
// tails that group by sender, and a glass text box that sits on the keyboard (main.tsx).
export function Conversation({ did, contact, name, onBack, onCall, onSent }: {
  did: string;
  contact: string;
  name?: string;
  onBack: () => void;
  onCall: () => void;
  onSent: () => void;
}) {
  // The texts start from what the device kept (store.ts), and the HQ then brings them up to date.
  const [texts, setTexts] = useState<Text[] | null>(() => kept(`texts.${did}.${contact}`));
  const [draft, setDraft] = useState("");
  // The picture in the text box, as a data URL, until it goes.
  const [picture, setPicture] = useState("");
  const chooser = useRef<HTMLInputElement>(null);
  const [outbox, setOutbox] = useState<Outgoing[]>([]);
  const [error, setError] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const foot = useRef<HTMLDivElement>(null);
  // True while the last text is in view. Then a new text, and the keyboard, keep it in view.
  const atEnd = useRef(true);
  const touchY = useRef(0);

  const load = useCallback(() => {
    api.thread(did, contact).then((r) => setTexts(r.texts), (e) => setError(e.message));
  }, [did, contact]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [load]);
  useEffect(() => void (texts && keep(`texts.${did}.${contact}`, texts)), [texts]);

  const toEnd = () => {
    const el = scroller.current;
    if (el && atEnd.current) el.scrollTop = el.scrollHeight;
  };
  useLayoutEffect(toEnd, [texts?.length, outbox.length]);
  // The keyboard makes the list shorter. The last text stays above the text box.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const keep = new ResizeObserver(toEnd);
    keep.observe(el);
    return () => keep.disconnect();
  }, []);

  // The texts end above the text box, which grows with its text.
  useEffect(() => {
    const el = foot.current;
    if (!el) return;
    const room = new ResizeObserver(() => el.parentElement?.style.setProperty("--foot", `${el.offsetHeight}px`));
    room.observe(el);
    return () => room.disconnect();
  }, []);

  // The box grows with the text, up to the max-height of app.css.
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

  const deliver = async (item: Outgoing) => {
    const mark = (failed: boolean) => setOutbox((o) => o.map((x) => (x.key === item.key ? { ...x, failed } : x)));
    mark(false);
    try {
      const r = await api.send(did, contact, item.body, item.media);
      setTexts(r.texts);
      setOutbox((o) => o.filter((x) => x.key !== item.key));
      onSent();
    } catch {
      mark(true);
    }
  };

  // The text shows at once and the box is empty for the next one. The HQ answers in the background.
  const send = () => {
    const body = draft.trim();
    if (!body && !picture) return;
    const item = { key: Date.now() + Math.random(), body, media: picture || undefined, at: new Date().toISOString() };
    atEnd.current = true;
    setDraft("");
    setPicture("");
    setOutbox((o) => [...o, item]);
    void deliver(item);
  };

  // A poll can bring a text in before its own answer does. It then shows once, from the server.
  const pending = outbox.filter((item) => item.failed || !texts?.some((t) =>
    !t.incoming && t.body === item.body && Math.abs(new Date(t.at).getTime() - new Date(item.at).getTime()) < 60000));
  const rows: Row[] = [
    ...(texts ?? []).map((t) => ({ key: `t${t.id}`, incoming: t.incoming, body: t.body, media: t.media, at: t.at })),
    ...pending.map((o) => ({ key: `o${o.key}`, incoming: false, body: o.body, media: o.media ? [o.media] : [], at: o.at, out: o })),
  ];

  return (
    <div className="page convo">
      <div className="bubbles" ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
        // A drag down on the texts hides the keyboard, as in Messages.
        onTouchStart={(e) => (touchY.current = e.touches[0].clientY)}
        onTouchMove={(e) => {
          if (e.touches[0].clientY - touchY.current > 10) field.current?.blur();
        }}>
        {rows.map((row, i) => {
          const before = rows[i - 1];
          const after = rows[i + 1];
          const stamp = !before || apart(before, row);
          const [day, time] = stampTime(row.at);
          // The first bubble of a run from one side has space over it. The last one has the tail.
          const first = stamp || before.incoming !== row.incoming;
          const tail = !after || after.incoming !== row.incoming || apart(row, after);
          // A picture shows alone, over its text, as in Messages.
          const side = row.incoming ? "in" : "out";
          const photo = row.media.length > 0;
          const kind = `bubble ${side}${first && !photo ? " first" : ""}${tail ? " tail" : ""}`;
          return (
            <Fragment key={row.key}>
              {stamp && <p className="stamp"><b>{day}</b> {time}</p>}
              {row.out?.failed ? (
                <div className="failed" onClick={() => void deliver(row.out!)}>
                  <div className="failed-row">
                    <div className={kind}>{row.body}</div>
                    <span className="alert" aria-label="Send again">!</span>
                  </div>
                  <p>Not Delivered</p>
                </div>
              ) : (
                <>
                  {photo && (
                    <div className={`bubble ${side} photo${first ? " first" : ""}`}>
                      {/* VoIP.ms forgets the picture of some texts, and a broken picture shows nothing. */}
                      {row.media.map((url) => <img key={url} src={url} alt="" onError={(e) => (e.currentTarget.style.display = "none")} />)}
                    </div>
                  )}
                  {row.body && <div className={kind}>{row.body}</div>}
                </>
              )}
            </Fragment>
          );
        })}
      </div>
      <header className="convo-head">
        <button className="glass round" onClick={onBack} aria-label="Back"><Icon name="back" /></button>
        <div className="who">
          <span className="avatar">{initials(name) || <Icon name="person" size={26} />}</span>
          <span className="glass pill">{name || pretty(contact)}</span>
        </div>
        <button className="glass round" onClick={onCall} aria-label="Call"><Icon name="phone" /></button>
      </header>
      <div className="composer" ref={foot}>
        {error && <p className="error">{error}</p>}
        <div className="composer-row">
        {/* The + of Messages. The file field opens the picker of the system: on the iPhone the photo library, the
            camera or a file, and on the Mac a file. */}
        <button className="glass round plus" onClick={() => chooser.current?.click()} aria-label="Add a photo">
          <Icon name="plus" size={20} />
        </button>
        <input ref={chooser} type="file" accept="image/*" hidden onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) shrink(file).then(setPicture, () => setError("That picture cannot be read."));
        }} />
        <div className="glass field">
          {picture && (
            <div className="attached">
              <img src={picture} alt="" />
              <button onClick={() => setPicture("")} aria-label="Remove the photo">×</button>
            </div>
          )}
          <div className="field-row">
          <textarea ref={field} rows={1} value={draft} placeholder="Text Message • SMS" onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }} />
          {(draft.trim() || picture) && (
            <button className="send" onClick={send} aria-label="Send"><Icon name="send" size={17} /></button>
          )}
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}
