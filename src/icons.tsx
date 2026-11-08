// The icons of the app: SF Symbols-like strokes, 24 by 24, in the color of the text.
const PATHS = {
  messages: "M4 5.5C4 4.7 4.7 4 5.5 4h13c.8 0 1.5.7 1.5 1.5v9c0 .8-.7 1.5-1.5 1.5H10l-4.5 4v-4h0c-.8 0-1.5-.7-1.5-1.5z",
  phone: "M6.6 3.5h2.6l1.5 4-2 1.5a11 11 0 0 0 6.3 6.3l1.5-2 4 1.5v2.6c0 1-.8 1.7-1.8 1.6A16.5 16.5 0 0 1 5 5.3c-.1-1 .6-1.8 1.6-1.8z",
  keypad: "M6 5h.01M12 5h.01M18 5h.01M6 11h.01M12 11h.01M18 11h.01M6 17h.01M12 17h.01M18 17h.01",
  compose: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  back: "M15 5l-7 7 7 7",
  next: "M9 5l7 7-7 7",
  plus: "M12 5v14M5 12h14",
  search: "M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zM16.5 16.5L21 21",
  down: "M6 9l6 6 6-6",
  send: "M12 19V5M5 12l7-7 7 7",
  person: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20c0-3.3 3.6-6 8-6s8 2.7 8 6",
  mute: "M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M4 4l16 16",
  erase: "M9 5h11v14H9l-6-7zM12 9l5 6M17 9l-5 6",
  check: "M5 12l5 5 9-10",
  lock: "M7.5 11V8a4.5 4.5 0 0 1 9 0v3M6 11h12v9H6z",
  incoming: "M17 7L7 17M7 9v8h8",
  outgoing: "M7 17L17 7M9 7h8v8",
  voicemail: "M6.5 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM17.5 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM6.5 15.5h11",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 22 }: { name: IconName; size?: number }) {
  const dots = name === "keypad";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={dots ? 3.4 : 1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={PATHS[name]} />
    </svg>
  );
}
