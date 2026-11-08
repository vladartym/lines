// What Lines keeps on the device, so a list shows at once at the next start, also with no network, and the HQ then
// brings it up to date. The lists go in localStorage. The audio of the voicemail goes in IndexedDB, which holds more.
// A device that refuses to keep something (full, or private) loads it from the HQ as before.

export function kept<T>(key: string): T | null {
  try {
    const value = localStorage.getItem(`lines.kept.${key}`);
    return value ? (JSON.parse(value) as T) : null;
  } catch {
    return null;
  }
}

export function keep(key: string, value: unknown) {
  try {
    localStorage.setItem(`lines.kept.${key}`, JSON.stringify(value));
  } catch {
    // Full: the list loads from the HQ as before.
  }
}

// Opened at the first use. Just after a reload, WebKit can leave an open with no answer, so an open that takes more
// than 3 seconds fails, the audio comes from the HQ as before, and the next use opens it again.
let opened: Promise<IDBDatabase> | null = null;
function database(): Promise<IDBDatabase> {
  if (!opened) {
    opened = new Promise<IDBDatabase>((ok, no) => {
      const open = indexedDB.open("lines", 1);
      open.onupgradeneeded = () => open.result.createObjectStore("audio");
      open.onsuccess = () => ok(open.result);
      open.onerror = () => no(open.error);
      setTimeout(() => no(new Error("IndexedDB did not answer")), 3000);
    });
    opened.catch(() => (opened = null));
  }
  return opened;
}

function audio<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return database().then((d) => new Promise<T>((ok, no) => {
    const request = work(d.transaction("audio", mode).objectStore("audio"));
    request.onsuccess = () => ok(request.result);
    request.onerror = () => no(request.error);
  }));
}

// The MP3 of one voicemail message, as the data URL that the HQ sent.
export const keptAudio = (key: string) => audio<string | undefined>("readonly", (s) => s.get(key)).catch(() => undefined);
export const keepAudio = (key: string, mp3: string) => audio("readwrite", (s) => s.put(mp3, key)).catch(() => {});
export const keptAudioKeys = () =>
  audio<IDBValidKey[]>("readonly", (s) => s.getAllKeys()).then((k) => k.map(String), (): string[] => []);
export const forgetAudio = (key: string) => audio("readwrite", (s) => s.delete(key)).catch(() => {});
