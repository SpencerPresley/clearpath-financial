/*
 * Whether the page area (#main, the shell's <main>) is narrower than a width. Pages use it for layout that CSS
 * container queries can't do alone, e.g. the queue dropping table columns whose widths are set in JS. #main
 * narrows when the nav expands or the assistant panel opens, which a viewport media query can't see.
 */
import { useEffect, useState } from 'react';

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
