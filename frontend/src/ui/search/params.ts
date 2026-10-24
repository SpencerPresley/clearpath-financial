/*
 * Zod guards for URL search params (decisions.md "Stack": filters live in validated URL search params). Each
 * field is .catch()-guarded, so a stale or hand-edited URL drops the bad field and still renders instead of
 * throwing the route into its error boundary. Same rules as the queue's schema (features/queue/search.ts),
 * shared here so other screens don't import a feature.
 */
import { z } from 'zod';

/** A list of enum values; unknown entries are dropped, and an empty list reads as absent. */
export function enumList<T extends string>(values: readonly T[]) {
  const allowed = new Set<string>(values);
  return z
    .array(z.unknown())
    .transform((list) => {
      const kept = list.filter((v): v is T => typeof v === 'string' && allowed.has(v));
      return kept.length > 0 ? kept : undefined;
    })
    .optional()
    .catch(undefined);
}

/** Positive integer ids; an empty list reads as absent. */
export const idList = z
  .array(z.number().int().positive())
  .transform((list) => (list.length > 0 ? list : undefined))
  .optional()
  .catch(undefined);

export const flag = z.boolean().optional().catch(undefined);

/** A calendar date, `YYYY-MM-DD`. */
export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((value) => !Number.isNaN(new Date(`${value}T00:00:00Z`).getTime()))
  .optional()
  .catch(undefined);

/** Free text with a length cap; blank reads as absent. */
export function text(max: number) {
  return z
    .string()
    .max(max)
    .transform((value) => (value.trim() === '' ? undefined : value))
    .optional()
    .catch(undefined);
}

/** `YYYY-MM-DD` → the next day, for exclusive upper bounds (`approved_before`). */
export function nextDay(date: string): string {
  const next = new Date(`${date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString().slice(0, 10);
}
