/*
 * Notification rows for the inbox's unit tests, e2e flow, and UI-review screenshots. Times are relative to
 * NOW in review.ts's frame (2026-10-24 15:00Z), so "Today" and "Earlier" are stable.
 */
import type { NotificationOut, NotificationPageOut } from '../../api/generated/model';

export const DANA = { id: 21, name: 'Dana Reyes' };
export const SAM = { id: 22, name: 'Sam Okafor' };
export const PRIYA = { id: 23, name: 'Priya Raman' };

const base = {
  read_at: null,
  item_id: 42,
  item_key: 'CP-42',
  item_title: 'Fall personal loan promo',
  message: 'CP-42 Fall personal loan promo',
} satisfies Partial<NotificationOut>;

export function notificationFixture(overrides: Partial<NotificationOut> = {}): NotificationOut {
  return {
    ...base,
    id: 1,
    kind: 'decision',
    actor: DANA,
    detail: { kind: 'decision', outcome: 'changes_requested' },
    created_at: '2026-10-24T14:48:00Z',
    ...overrides,
  };
}

/** The inbox at a glance: today's unread work on top, older read rows below. */
export const INBOX_ROWS: NotificationOut[] = [
  notificationFixture({ id: 9 }),
  notificationFixture({
    id: 8,
    kind: 'mention',
    actor: SAM,
    item_id: 1042,
    item_key: 'CP-1042',
    item_title: 'Spring balance transfer email',
    detail: { kind: 'mention', comment_id: 311, version_n: 2 },
    created_at: '2026-10-24T13:05:00Z',
  }),
  notificationFixture({
    id: 7,
    kind: 'assignment',
    actor: PRIYA,
    item_id: 1051,
    item_key: 'CP-1051',
    item_title: 'LendRight comparison page',
    detail: { kind: 'assignment', mode: 'manual' },
    created_at: '2026-10-24T09:30:00Z',
  }),
  notificationFixture({
    id: 6,
    kind: 'rereview',
    actor: PRIYA,
    item_id: 1007,
    item_key: 'CP-1007',
    item_title: 'Debt consolidation landing page',
    detail: { kind: 'rereview', reason: 'terms_changed' },
    created_at: '2026-10-23T16:20:00Z',
    read_at: '2026-10-23T17:00:00Z',
  }),
  notificationFixture({
    id: 5,
    kind: 'expiry_warning',
    actor: null,
    item_id: 988,
    item_key: 'CP-988',
    item_title: 'Home improvement loan banner',
    detail: { kind: 'expiry_warning', expires_at: '2026-11-23T15:00:00Z' },
    created_at: '2026-10-22T06:00:00Z',
    read_at: '2026-10-22T08:00:00Z',
  }),
  notificationFixture({
    id: 4,
    kind: 'decision',
    actor: DANA,
    item_id: 1003,
    item_key: 'CP-1003',
    item_title: 'Card rewards social post',
    detail: { kind: 'decision', outcome: 'approved' },
    created_at: '2026-10-20T11:10:00Z',
    read_at: '2026-10-20T12:00:00Z',
  }),
];

export function pageOf(rows: NotificationOut[]): NotificationPageOut {
  return { rows, unread_count: rows.filter((row) => row.read_at === null).length };
}

export const EMPTY_PAGE: NotificationPageOut = { rows: [], unread_count: 0 };
