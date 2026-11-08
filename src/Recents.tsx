// The calls of the last 30 days, from the call records of VoIP.ms. A tap calls the number back.
import type { Call } from "./api";
import { duration, listTime, pretty } from "./format";
import { Icon } from "./icons";

export function Recents({ calls, names, onCall }: {
  calls: Call[] | null;
  names: Map<string, string>;
  onCall: (number: string) => void;
}) {
  if (!calls) return <p className="empty">Loading</p>;
  if (!calls.length) return <p className="empty">No calls</p>;
  return (
    <ul className="list">
      {calls.map((c) => (
        <li key={c.id} className="row" onClick={() => c.number && onCall(c.number)}>
          <span className="muted"><Icon name={c.incoming ? "incoming" : "outgoing"} size={16} /></span>
          <div className="row-main">
            <div className="row-top">
              <b className={c.incoming && !c.answered ? "missed" : ""}>{names.get(c.number) || pretty(c.number) || "No Caller ID"}</b>
              <span className="muted small">{listTime(c.at)}</span>
            </div>
            <span className="muted small">{c.answered ? duration(c.seconds) : c.incoming ? "Missed" : "No answer"}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
