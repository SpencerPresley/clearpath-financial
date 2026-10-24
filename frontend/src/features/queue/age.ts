/*
 * Queue age: time since the item last entered the queue (`queue_entered_at`: submission, resubmission, new round
 * or reopen), shared by the table's Age column, the board cards and the preview drawer (walkthrough S4).
 */
import type { ItemRowOut } from '../../api/generated/model';
import { formatDateTime } from '../../ui/labels';
import { formatAge } from '../../ui/RelativeAge';

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Time in the queue, compact. Under a week it keeps one decimal, rounded up, so an item listed under "Waiting
 * >3 days" never reads "3d" (walkthrough nit 1): 3 days and 2 hours is "3.1d". Otherwise as `formatAge`.
 */
export function formatQueueAge(at: Date, now: Date): string {
  const days = (now.getTime() - at.getTime()) / DAY_MS;
  if (days < 1 || days >= 7) return formatAge(at, now);
  return `${(Math.ceil(days * 10) / 10).toFixed(1)}d`;
}

/** The age tooltip: when the item entered the queue, and its last submission when that was earlier (a reopen). */
export function ageTitle(row: Pick<ItemRowOut, 'queue_entered_at' | 'submitted_at'>): string {
  const since = `In the queue since ${formatDateTime(row.queue_entered_at)}`;
  return new Date(row.submitted_at).getTime() < new Date(row.queue_entered_at).getTime()
    ? `${since} · last submitted ${formatDateTime(row.submitted_at)}`
    : since;
}
