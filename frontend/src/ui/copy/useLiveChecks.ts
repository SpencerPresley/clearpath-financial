import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { previewChecks } from '../../api/generated/findings/findings';
import type { CheckPreviewIn, FindingDraftOut } from '../../api/generated/model';
import { marksFromFindings } from './marks';
import { visibleMarks } from './segments';
import type { SpanMark } from './segments';

/**
 * Spec §4.3: findings appear under 300 ms after the marketer stops typing. That's the whole budget, so the
 * debounce is 150 ms and the rest is left for the request (the engine takes ~3 ms on a 5 KB ad).
 */
export const LIVE_CHECK_DEBOUNCE_MS = 150;

export type LiveCheckStatus = 'idle' | 'checking' | 'ready' | 'error';

export interface LiveChecks {
  /** Findings for `checkedText` (the last text the server checked), blocking first as the API orders them. */
  findings: FindingDraftOut[];
  /** Marks for the *current* text: findings whose quote no longer sits at its span are hidden. */
  marks: SpanMark[];
  status: LiveCheckStatus;
  checkedText: string | null;
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, delayMs]);
  return debounced;
}

/**
 * Runs `POST /checks/preview` as the copy changes. Keyed on the serialized input, so React Query cancels
 * the superseded request (via `signal`) and an identical text is answered from cache.
 */
export function useLiveChecks(input: CheckPreviewIn | null, delayMs = LIVE_CHECK_DEBOUNCE_MS): LiveChecks {
  const key = input === null || input.content_text.trim() === '' ? null : JSON.stringify(input);
  const debouncedKey = useDebounced(key, delayMs);

  const query = useQuery({
    queryKey: ['previewChecks', debouncedKey],
    queryFn: async ({ signal }) => {
      const body = JSON.parse(debouncedKey ?? 'null') as CheckPreviewIn;
      const result = await previewChecks(body, { signal });
      return { text: body.content_text, findings: result.findings };
    },
    enabled: debouncedKey !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });

  const currentText = input?.content_text ?? '';
  const data = key === null ? undefined : query.data;

  const marks = useMemo(
    () => (data === undefined ? [] : visibleMarks(currentText, marksFromFindings(data.text, data.findings))),
    [data, currentText],
  );

  let status: LiveCheckStatus;
  if (key === null) {
    status = 'idle';
  } else if (query.isError) {
    status = 'error';
  } else if (key !== debouncedKey || query.isFetching || data === undefined) {
    status = 'checking';
  } else {
    status = 'ready';
  }

  return { findings: data?.findings ?? [], marks, status, checkedText: data?.text ?? null };
}
