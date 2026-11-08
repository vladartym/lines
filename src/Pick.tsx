// Pick a contact or type a number: for a new text, and for a call from the keypad.
import { useMemo, useState } from "react";
import { digits, pretty } from "./format";
import type { Contact } from "./native";

export function Pick({ title, contacts, onPick, onCancel }: {
  title: string;
  contacts: Contact[];
  onPick: (number: string) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const typed = digits(query);
  const found = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((c) => c.name.toLowerCase().includes(q) || (typed && digits(c.number).includes(typed)));
  }, [contacts, query, typed]);

  return (
    <div className="page">
      <header className="bar">
        <span className="bar-side" />
        <h2>{title}</h2>
        <button className="link bar-side end" onClick={onCancel}>Cancel</button>
      </header>
      <div className="to">
        <span>To:</span>
        <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name or number"
          inputMode="text" autoCorrect="off" autoCapitalize="off"
          onKeyDown={(e) => e.key === "Enter" && typed.length >= 3 && onPick(typed)} />
      </div>
      <ul className="list scroll">
        {typed.length >= 3 && (
          <li className="row" onClick={() => onPick(typed)}>
            <div className="row-main"><b>{pretty(typed)}</b></div>
          </li>
        )}
        {found.map((c, i) => (
          <li key={`${c.number}-${i}`} className="row" onClick={() => onPick(digits(c.number))}>
            <div className="row-main">
              <b>{c.name || pretty(c.number)}</b>
              <span className="muted">{c.label ? `${c.label} ` : ""}{pretty(c.number)}</span>
            </div>
          </li>
        ))}
        {!found.length && typed.length < 3 && <li className="empty">No contacts</li>}
      </ul>
    </div>
  );
}
