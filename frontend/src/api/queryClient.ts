import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './mutator';

const MAX_RETRIES = 3;

/**
 * Retry only what can change on a second try: a 5xx or a request that never reached the server. A 4xx (not
 * permitted, not found, invalid) gets the same answer again, so the page shows it at once instead of after
 * ~7 s of backoff behind a skeleton.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < MAX_RETRIES;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: true,
        retry: shouldRetry,
      },
    },
  });
}
