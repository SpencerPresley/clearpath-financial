/*
 * The reviewer's queue order, carried from the queue to the review screen so "Next item" (j) opens the next row
 * of the view they came from (spec §4.3 Review: navigate the queue without the mouse). The queue writes the
 * list it shows (its request params, the row order and its own URL); the review screen reads it.
 *
 * Session storage, per tab: a second tab on another view keeps its own order, and nothing outlives the session.
 * The queue and review features can't import each other (frontend/CLAUDE.md), so the contract lives here.
 */
import type { ItemStatus, ListItemsParams } from '../api/generated/model';

export interface QueueTrail {
  /** GET /items params of the view, without paging. */
  params: ListItemsParams;
  /** Row ids in the order the queue showed them. */
  ids: number[];
  /** The queue URL to return to when the view runs out. */
  href: string;
}

const KEY = 'clearpath.queueTrail';

/** The review queue's statuses (backend reviews.models.QUEUE_STATUSES). */
const QUEUED: ItemStatus[] = ['submitted', 'in_review', 'needs_rereview'];

/**
 * Opened without the queue (a link, a notification): the queue's default view, My queue. queue/search.test.ts
 * checks this against the queue's own definition of that view.
 */
export const DEFAULT_TRAIL: QueueTrail = {
  params: { status: QUEUED, is_legacy: false, mine: true, sort: 'queue' },
  ids: [],
  href: '/queue',
};

export function rememberQueueTrail(trail: QueueTrail): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(trail));
  } catch {
    // Storage full or disabled: Next item falls back to My queue.
  }
}

function isTrail(value: unknown): value is QueueTrail {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.params === 'object' &&
    v.params !== null &&
    Array.isArray(v.ids) &&
    v.ids.every((id) => typeof id === 'number') &&
    typeof v.href === 'string' &&
    v.href.startsWith('/queue')
  );
}

export function readQueueTrail(): QueueTrail {
  try {
    const raw = sessionStorage.getItem(KEY);
    const parsed: unknown = raw === null ? null : JSON.parse(raw);
    return isTrail(parsed) ? parsed : DEFAULT_TRAIL;
  } catch {
    return DEFAULT_TRAIL;
  }
}

/**
 * The item after `currentId` in the view as it is now (`fresh`, re-fetched), keeping the order the reviewer was
 * working through (`seen`, the trail). A decided item usually leaves the view, so when it's gone the next one is
 * the first fresh row that came after it in the trail; rows the reviewer skipped earlier come last.
 * Null when nothing else is left.
 */
export function nextInQueue(
  currentId: number,
  fresh: readonly number[],
  seen: readonly number[],
): number | null {
  const others = fresh.filter((id) => id !== currentId);
  const at = fresh.indexOf(currentId);
  if (at !== -1) {
    return fresh[at + 1] ?? others[0] ?? null;
  }
  const seenAt = seen.indexOf(currentId);
  if (seenAt !== -1) {
    const after = new Set(seen.slice(seenAt + 1));
    const next = fresh.find((id) => after.has(id));
    if (next !== undefined) return next;
  }
  return others[0] ?? null;
}
