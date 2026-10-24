/*
 * Whether the page area (#main, the shell's <main>) is narrower than a width. Pages use it for layout that CSS
 * container queries can't do alone, e.g. the queue dropping table columns whose widths are set in JS. #main
 * narrows when the nav expands or the assistant panel opens, which a viewport media query can't see.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export function useMainNarrowerThan(px: number): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const main = document.getElementById('main');
    if (main === null || typeof ResizeObserver !== 'function') return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width !== undefined) setNarrow(width < px);
    });
    observer.observe(main);
    return () => {
      observer.disconnect();
    };
  }, [px]);
  return narrow;
}

/**
 * An element's inner width (clientWidth: inside borders and scrollbar), kept current. Pass the returned ref to
 * the element; null until it has been laid out (jsdom reports 0, which counts as not measured). Measured in the
 * ref callback, during commit, so the first paint already uses it.
 */
export function useElementWidth(): [(element: HTMLElement | null) => void, number | null] {
  const [width, setWidth] = useState<number | null>(null);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = useCallback((element: HTMLElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (element === null) return;
    const read = () => {
      setWidth(element.clientWidth > 0 ? element.clientWidth : null);
    };
    read();
    if (typeof ResizeObserver !== 'function') return;
    observer.current = new ResizeObserver(read);
    observer.current.observe(element);
  }, []);
  return [ref, width];
}
