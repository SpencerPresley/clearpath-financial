import { useCallback, useSyncExternalStore } from 'react';

/** Whether a media query matches, live. False where matchMedia doesn't exist (jsdom). */
export function useMediaQuery(query: string): boolean {
  const supported = typeof window.matchMedia === 'function';
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!supported) return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => {
        list.removeEventListener('change', onChange);
      };
    },
    [query, supported],
  );
  return useSyncExternalStore(
    subscribe,
    () => supported && window.matchMedia(query).matches,
    () => false,
  );
}
