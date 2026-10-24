/*
 * One line for a failed request (spec §5.4: what happened, and what to do). The API's ErrorOut.message is
 * already written that way, so it wins; otherwise fall back to the caller's sentence.
 */
import { ApiError } from '../api/mutator';

function bodyMessage(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('message' in body)) return undefined;
  const message = body.message;
  return typeof message === 'string' && message.trim() !== '' ? message : undefined;
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return bodyMessage(error.body) ?? fallback;
  }
  if (error instanceof TypeError) {
    // fetch rejects with TypeError when the network is down or the server is unreachable.
    return "Can't reach the server. Check your connection and try again.";
  }
  return fallback;
}

export function errorStatus(error: unknown): number | undefined {
  return error instanceof ApiError ? error.status : undefined;
}
