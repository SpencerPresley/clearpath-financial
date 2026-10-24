/*
 * Reading the API's error body (core.schemas.ErrorOut: {code, message, details, fields}) off the mutator's
 * ApiError. Forms are where a 422 can be decided (spec §6.1): field issues go on fields, the rest on the
 * form. Everything else propagates to the caller's onError.
 */
import type { ErrorOut } from '../../api/generated/model';
import { ApiError } from '../../api/mutator';

export function apiErrorBody(error: unknown): ErrorOut | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  const body = error.body;
  if (typeof body === 'object' && body !== null && 'code' in body && 'message' in body) {
    return body as ErrorOut;
  }
  return undefined;
}

/** One line saying what happened (spec §5.4); the server's message when it sent one. */
export function apiErrorMessage(error: unknown): string {
  const body = apiErrorBody(error);
  if (body !== undefined) {
    return body.message;
  }
  if (error instanceof ApiError) {
    return error.status >= 500
      ? 'The server had a problem. Try again in a minute.'
      : `Request failed (${String(error.status)}). Try again.`;
  }
  return "Couldn't reach the server. Check your connection and try again.";
}

export interface FormErrors {
  fields: Record<string, string>;
  form: string | null;
}

/** Maps `ErrorOut.fields[].loc` to the last loc segment that names one of `fields`. */
export function fieldErrorsFrom(error: unknown, fields: readonly string[]): FormErrors {
  const body = apiErrorBody(error);
  const known = new Set(fields);
  const result: Record<string, string> = {};
  const unmapped: string[] = [];

  for (const issue of body?.fields ?? []) {
    const name = [...issue.loc].reverse().find((part) => typeof part === 'string' && known.has(part));
    if (typeof name === 'string' && result[name] === undefined) {
      result[name] = issue.message;
    } else if (typeof name !== 'string') {
      unmapped.push(issue.message);
    }
  }

  let form: string | null = unmapped.length > 0 ? unmapped.join(' ') : null;
  if (form === null && Object.keys(result).length === 0) {
    form = apiErrorMessage(error);
  }
  return { fields: result, form };
}
