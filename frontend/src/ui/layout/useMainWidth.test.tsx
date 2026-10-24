import { act, render, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useMainNarrowerThan } from './useMainWidth';
import { useMediaQuery } from './useMediaQuery';

type Callback = (entries: { contentRect: { width: number } }[]) => void;

describe('useMainNarrowerThan', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('follows the width of #main', () => {
    let notify: Callback = () => undefined;
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: Callback) {
          notify = callback;
        }
        observe() {
          /* driven by notify */
        }
        disconnect() {
          /* nothing to release */
        }
      },
    );
    render(<main id="main" />);
    const { result } = renderHook(() => useMainNarrowerThan(1000));
    expect(result.current).toBe(false);
    act(() => {
      notify([{ contentRect: { width: 828 } }]);
    });
    expect(result.current).toBe(true);
    act(() => {
      notify([{ contentRect: { width: 1064 } }]);
    });
    expect(result.current).toBe(false);
  });

  it('is false where ResizeObserver or #main is missing', () => {
    vi.stubGlobal('ResizeObserver', undefined);
    const { result } = renderHook(() => useMainNarrowerThan(1000));
    expect(result.current).toBe(false);
  });
});

describe('useMediaQuery', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads matchMedia and is false without it', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(width < 1600px)',
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    expect(renderHook(() => useMediaQuery('(width < 1600px)')).result.current).toBe(true);
    expect(renderHook(() => useMediaQuery('(width < 900px)')).result.current).toBe(false);
    vi.stubGlobal('matchMedia', undefined);
    expect(renderHook(() => useMediaQuery('(width < 1600px)')).result.current).toBe(false);
  });
});
