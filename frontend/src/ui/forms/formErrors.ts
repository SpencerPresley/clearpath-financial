/*
 * Bridges between TanStack Form's error shapes and the fields in fields.tsx. Schema validators (Standard
 * Schema, e.g. zod) put issue objects in `field.state.meta.errors`; server errors a page puts in a field's
 * `errorMap.onServer` (from `fieldErrorsFrom`) are strings. Fields take one string.
 */

/** The first error to show under a field, whichever shape it arrived in. */
export function fieldErrorText(errors: readonly unknown[]): string | undefined {
  for (const error of errors) {
    if (typeof error === 'string' && error !== '') {
      return error;
    }
    if (typeof error === 'object' && error !== null && 'message' in error) {
      const message = error.message;
      if (typeof message === 'string' && message !== '') {
        return message;
      }
    }
  }
  return undefined;
}
