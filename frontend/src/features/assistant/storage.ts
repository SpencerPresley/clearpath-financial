/*
 * Panel state that survives a reload: whether the panel is open, and each user's active thread. Same guard as
 * the nav collapse (AppShell): storage can be blocked (privacy mode), and then the choice lasts for this view.
 */

export const ASSISTANT_OPEN_KEY = 'clearpath.assistant.open';
export const ASSISTANT_PANEL_ID = 'assistant-panel';
/** Window event asking the shell to open the panel on a thread (`detail.threadId`), e.g. from the Outbox. */
export const ASSISTANT_OPEN_EVENT = 'clearpath:assistant-open';

export function threadKey(userId: number): string {
  return `clearpath.assistant.thread.${String(userId)}`;
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // storage blocked: keep the in-memory state only
  }
}

export function readAssistantOpen(): boolean {
  return read(ASSISTANT_OPEN_KEY) === 'true';
}

export function writeAssistantOpen(open: boolean) {
  write(ASSISTANT_OPEN_KEY, String(open));
}

export function readActiveThread(userId: number): string | null {
  const value = read(threadKey(userId));
  return value === null || value === '' ? null : value;
}

export function writeActiveThread(userId: number, threadId: string | null) {
  write(threadKey(userId), threadId);
}

/** Open the panel on `threadId` (remembered first, so a panel that mounts now starts there). */
export function openAssistantThread(userId: number, threadId: string) {
  writeActiveThread(userId, threadId);
  window.dispatchEvent(new CustomEvent(ASSISTANT_OPEN_EVENT, { detail: { threadId } }));
}

/** Open the panel where it was (from the Outbox's empty state). */
export function openAssistant() {
  window.dispatchEvent(new CustomEvent(ASSISTANT_OPEN_EVENT, { detail: {} }));
}
