// Numbers and times the way an iPhone shows them.

// The 10 digits that the API takes, from whatever was typed, pasted or saved in a contact.
export function digits(number: string): string {
  const d = String(number || "").replace(/\D/g, "");
  return d.length === 11 && d.startsWith("1") ? d.slice(1) : d;
}

// (416) 555-0123 for a North American number, the digits as given otherwise, such as a short code.
export function pretty(number: string): string {
  const ten = digits(number);
  if (ten.length !== 10) return number;
  return `(${ten.slice(0, 3)}) ${ten.slice(3, 6)}-${ten.slice(6)}`;
}

const DAY = 86400000;

function daysAgo(date: Date): number {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  return Math.floor((start.getTime() - date.getTime()) / DAY) + 1;
}

function clock(date: Date): string {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// The time on the right of a row: 9:41 AM, Yesterday, Saturday, or 10/3/26.
export function listTime(iso: string): string {
  const date = new Date(iso);
  const ago = daysAgo(date);
  if (ago <= 0) return clock(date);
  if (ago === 1) return "Yesterday";
  if (ago < 7) return date.toLocaleDateString([], { weekday: "long" });
  return date.toLocaleDateString([], { year: "2-digit", month: "numeric", day: "numeric" });
}

// The time over a run of texts, as the day and the time: Today 9:41 AM, Yesterday 9:41 AM, Saturday 9:41 AM, or
// Sat, Oct 3 9:41 AM. Messages shows the day in bold.
export function stampTime(iso: string): [string, string] {
  const date = new Date(iso);
  const ago = daysAgo(date);
  if (ago <= 0) return ["Today", clock(date)];
  if (ago === 1) return ["Yesterday", clock(date)];
  if (ago < 7) return [date.toLocaleDateString([], { weekday: "long" }), clock(date)];
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const day = date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
  return [day, clock(date)];
}

// 0:07, 12:34 or 1:02:03.
export function duration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
