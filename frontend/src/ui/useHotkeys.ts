import { useEffect, useRef } from 'react';

export type HotkeyMap = Record<string, (event: KeyboardEvent) => void>;

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  if (tag === 'INPUT') {
    const type = (target as HTMLInputElement).type;
    return !['checkbox', 'radio', 'button', 'submit', 'reset', 'file'].includes(type);
  }
  return false;
}

/**
 * Single-key shortcuts for the page (spec §5.7: the reviewer's loop works without the mouse). Keys are
 * `KeyboardEvent.key` values ('n', '?', 'Escape'). Ignored while typing in a field, with Ctrl/Meta/Alt
 * held, and while a modal dialog is open, so a reason that contains "d" never dismisses a finding.
 */
export function useHotkeys(map: HotkeyMap, enabled = true): void {
  const mapRef = useRef(map);
  useEffect(() => {
    mapRef.current = map;
  });

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) {
        return;
      }
      if (isEditable(event.target)) {
        return;
      }
      if (
        document.querySelector(
          '[role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"], .app-modal-overlay',
        ) !== null
      ) {
        return;
      }
      const handler = mapRef.current[event.key];
      if (handler !== undefined) {
        event.preventDefault();
        handler(event);
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [enabled]);
}
