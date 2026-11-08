// The Settings: forward the calls of the numbers to a cell, so they ring as regular calls (asterisk/extensions.conf of
// the server). The server keeps them, so the Mac and the iPhone show the same.
import { useEffect, useState } from "react";
import { api, type Settings as Values } from "./api";
import { digits, pretty } from "./format";
import { Icon } from "./icons";

export function Settings({ onBack }: { onBack: () => void }) {
  const [values, setValues] = useState<Values | null>(null);
  const [number, setNumber] = useState("");
  const [error, setError] = useState("");

  const load = () =>
    api.settings().then((v) => {
      setValues(v);
      setNumber(pretty(v.forward_to));
    }, (e) => setError(e.message));
  useEffect(() => void load(), []);

  // The screen changes at once. A refusal shows its reason and puts back what the server has.
  const save = (next: Values) => {
    setValues(next);
    setError("");
    api.saveSettings(next).then((v) => {
      setValues(v);
      setNumber(pretty(v.forward_to));
    }, (e) => {
      setError(e.message);
      void load();
    });
  };

  return (
    <div className="page">
      <header className="bar">
        <button className="icon bar-side" onClick={onBack} aria-label="Back"><Icon name="back" /></button>
        <h2>Settings</h2>
        <span className="bar-side" />
      </header>
      <div className="scroll settings">
        <p className="section">Calls</p>
        <div className="group">
          <label className="cell">
            <span>Forward to my phone</span>
            <input type="checkbox" className="switch" disabled={!values} checked={values?.forward_on ?? false}
              onChange={(e) => values && save({ forward_to: digits(number), forward_on: e.target.checked })} />
          </label>
          <label className="cell">
            <span>Number</span>
            <input className="value" inputMode="tel" placeholder="(647) 555-0100" value={number} disabled={!values}
              onChange={(e) => setNumber(e.target.value)}
              onBlur={() => values && digits(number) !== values.forward_to && save({ forward_to: digits(number), forward_on: values.forward_on })}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
          </label>
        </div>
        <p className="footnote">Calls ring this number as regular calls, and Lines rings too.</p>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
