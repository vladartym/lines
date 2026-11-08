// The native parts: the contacts of the device (src-tauri/contacts.m), and the tab bar of iOS 26
// (gen/apple/Sources/lines/NativeTabs.swift). Each one fails quietly in a browser, where the page shows its own form.
import { registerForPushNotifications } from "@choochmeque/tauri-plugin-notifications-api";
import { invoke } from "@tauri-apps/api/core";
import { digits } from "./format";

export type Contact = { name: string; number: string; label: string };

export async function loadContacts(): Promise<Contact[]> {
  try {
    return JSON.parse(await invoke<string>("contacts"));
  } catch {
    return [];
  }
}

// The name of each number, by its 10 digits.
export function namesOf(contacts: Contact[]): Map<string, string> {
  return new Map(contacts.map((c) => [digits(c.number), c.name]));
}

// The state of the native controls: the open tab, whether they hide, and on the Mac also the line, every line with its
// unread count, and the button at the top right ("compose", "contact" or "").
export type NativeState = {
  tab: string;
  hidden: boolean;
  line: string;
  lines: { did: string; title: string; unread: number }[];
  action: string;
};

// True when the native tab bar shows (iOS 26 and macOS 26), so the page hides its own.
export async function nativeTabs(state: NativeState): Promise<boolean> {
  try {
    return await invoke<boolean>("native_tabs", { state: JSON.stringify(state) });
  } catch {
    return false;
  }
}

// The APNs token of the iPhone. The first call asks for the permission to notify. "" on the Mac, in a browser, and when
// the user says no.
export async function pushToken(): Promise<string> {
  if (!/iPhone/.test(navigator.userAgent)) return "";
  try {
    return await registerForPushNotifications();
  } catch {
    return "";
  }
}
