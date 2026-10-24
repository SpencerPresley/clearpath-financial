/*
 * Only server failures (5xx, network) get a Retry: a refusal (4xx) won't succeed on a second try. The page also
 * never sends the one refusal it can predict, a period that ends before it starts.
 */
import { errorStatus } from '../../ui/errorMessage';

export function isServerError(error: unknown): boolean {
  const status = errorStatus(error);
  return status === undefined || status >= 500;
}
