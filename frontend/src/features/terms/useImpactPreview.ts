/*
 * The impact preview for the values in the form. `POST /terms/impact-preview` writes nothing, so it runs as a
 * query keyed on the canonical values (`termsKey`), debounced while the lead types. The previous result stays
 * on screen (marked stale) while the next one loads, so the panel doesn't collapse between keystrokes.
 *
 * `ready` is the Save gate: true only when the result on screen was computed for exactly the values in the
 * form now. A result for 12.9 never unlocks publishing 12.99.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { previewTermsImpact } from '../../api/generated/terms/terms';
import type { TermsProduct, TermsValues } from './termsForm';
import { termsKey, valuesFromKey } from './termsForm';

export const PREVIEW_DEBOUNCE_MS = 300;

/** Prefix for every preview entry; `invalidateAfterPublish` and a 409 drop them. */
export const IMPACT_PREVIEW_KEY = '/api/terms/impact-preview';

export function useImpactPreview(product: TermsProduct, values: TermsValues | null) {
  const key = values === null ? null : termsKey(values);
  // The debounced key, not the values object: the key is stable across renders and decodes to the body.
  const [debounced, setDebounced] = useState<string | null>(null);

  useEffect(() => {
    if (key === null) return;
    const timer = window.setTimeout(() => {
      setDebounced(key);
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [key]);

  const query = useQuery({
    queryKey: [IMPACT_PREVIEW_KEY, product, debounced],
    queryFn: ({ signal }) => {
      if (debounced === null) throw new Error('No values to preview');
      return previewTermsImpact({ product, values: valuesFromKey(debounced) }, { signal });
    },
    enabled: key !== null && debounced !== null,
    placeholderData: keepPreviousData,
    staleTime: 0,
    retry: false,
  });

  const current = key !== null && debounced === key && !query.isPlaceholderData;
  return {
    query,
    /** A preview for exactly these values is on screen. */
    ready: current && query.isSuccess,
    /** The preview for these values failed (not an older one). */
    failed: current && query.isError,
    /** Waiting on the debounce or the request for these values. */
    checking: key !== null && !(current && (query.isSuccess || query.isError)),
  };
}
