// The keys of a phone. The keypad tab dials with them, and a call sends them as tones.
const KEYS: [string, string][] = [
  ["1", ""], ["2", "ABC"], ["3", "DEF"],
  ["4", "GHI"], ["5", "JKL"], ["6", "MNO"],
  ["7", "PQRS"], ["8", "TUV"], ["9", "WXYZ"],
  ["*", ""], ["0", "+"], ["#", ""],
];

export function Keys({ onKey }: { onKey: (key: string) => void }) {
  return (
    <div className="keys">
      {KEYS.map(([key, letters]) => (
        <button key={key} className="key" onClick={() => onKey(key)}>
          <span>{key}</span>
          <small>{letters}</small>
        </button>
      ))}
    </div>
  );
}
