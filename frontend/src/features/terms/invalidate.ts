/*
 * What a publish makes stale. Generated query keys are `['/api/terms']`, `['/api/terms/current']`,
 * `['/api/items', params]`, ...: separate first elements, so a `['/api/terms']` prefix would miss
 * `/api/terms/current`. Match on the path instead.
 *
 * The fan-out runs in the background (outbox beat every 2 s), so item statuses change a few seconds after the
 * 201; the queue refetches on focus and on its own staleTime after that.
 */
import type { QueryClient } from '@tanstack/react-query';

const AFTER_PUBLISH = ['/api/terms', '/api/items', '/api/library', '/api/partners'] as const;

function startsWithAny(key: readonly unknown[], prefixes: readonly string[]): boolean {
  const head = key[0];
  return typeof head === 'string' && prefixes.some((prefix) => head.startsWith(prefix));
}

export function invalidateAfterPublish(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => startsWithAny(query.queryKey, AFTER_PUBLISH),
  });
}

/** Terms and previews only: another lead published since the form loaded (409). */
export function invalidateTerms(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => startsWithAny(query.queryKey, ['/api/terms']),
  });
}
