/*
 * Notification rows for the inbox's unit tests, e2e flow, and UI-review screenshots. Times are in the frame of
 * review.ts's NOW (2026-10-24 15:00Z). The viewer is Priya Natarajan (CP-1042's owner, review.ts MARKETER), so
 * no row names her as the actor; CP-1042 matches the review fixture, so a row can open it in e2e.
 */
import type { NotificationOut, NotificationPageOut } from '../../api/generated/model';

export const DANA = { id: 21, name: 'Dana Reyes' };
export const SAM = { id: 22, name: 'Sam Okafor' };
export const LEE = { id: 31, name: 'Lee Chen' };

export function notificationFixture(overrides: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id: 1,
    kind: 'decision',
    actor: DANA,
    item_id: 42,
    item_key: 'CP-42',
    item_title: 'Fall personal loan promo',
    detail: { kind: 'decision', outcome: 'changes_requested' },
    message: 'CP-42 Fall personal loan promo: changes requested',
    read_at: null,
    created_at: '2026-10-24T14:48:00Z',
    ...overrides,
  };
}

/** The mention that e2e opens: CP-1042 (review.ts), comment on v2 (its current version). */
export const MENTION_ON_1042 = notificationFixture({
  id: 8,
  kind: 'mention',
  actor: SAM,
  item_id: 1042,
  item_key: 'CP-1042',
  item_title: 'Fall personal loan promo — paid social',
  detail: { kind: 'mention', comment_id: 311, version_n: 2 },
  message: 'CP-1042 Fall personal loan promo — paid social: you were mentioned',
  created_at: '2026-10-24T13:05:00Z',
});

/** The inbox at a glance: today's unread work on top, older read rows below. */
export const INBOX_ROWS: NotificationOut[] = [
  notificationFixture({
    id: 9,
    item_id: 1038,
    item_key: 'CP-1038',
    item_title: 'Spring balance transfer email',
  }),
  MENTION_ON_1042,
  notificationFixture({
    id: 7,
    kind: 'assignment',
    actor: LEE,
    item_id: 1051,
    item_key: 'CP-1051',
    item_title: 'LendRight comparison page',
    detail: { kind: 'assignment', mode: 'manual' },
    created_at: '2026-10-24T09:30:00Z',
  }),
  notificationFixture({
    id: 6,
    kind: 'rereview',
    actor: LEE,
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
    item_id: 1003,
    item_key: 'CP-1003',
    item_title: 'Card rewards social post',
    detail: { kind: 'decision', outcome: 'approved' },
    created_at: '2026-10-20T11:10:00Z',
    read_at: '2026-10-20T12:00:00Z',
  }),
];

const MANY_TITLES = [
  'Holiday debt consolidation search ads with the full APR range and the California license disclosure',
  'Credit builder card landing page',
  'Personal loan comparison table on BestRates',
  'Refinance your car loan email, October send',
  'Student loan refi affiliate banner',
  'Back-to-school personal loan push notification',
  'Home improvement loan TV script',
  'Balance transfer card partner review',
];

/** A busy inbox for the "many" screenshot: every kind, long titles, a full scroll. */
export const MANY_ROWS: NotificationOut[] = [
  ...INBOX_ROWS.slice(0, 3),
  notificationFixture({
    id: 30,
    kind: 'page_findings', // the drift monitor's alert
    actor: null,
    item_id: 1012,
    item_key: 'CP-1012',
    item_title: 'Personal loan rates, LendRight placement',
    detail: { kind: 'page_findings', new_blocking_count: 2 },
    created_at: '2026-10-24T08:10:00Z',
  }),
  notificationFixture({
    id: 31,
    kind: 'assignment',
    actor: null,
    item_id: 1063,
    item_key: 'CP-1063',
    item_title: MANY_TITLES[0],
    detail: { kind: 'assignment', mode: 'sticky' },
    created_at: '2026-10-24T07:45:00Z',
  }),
  notificationFixture({
    id: 32,
    actor: DANA,
    item_id: 1059,
    item_key: 'CP-1059',
    item_title: 'Spring promo display ads',
    detail: { kind: 'decision', outcome: 'rejected' },
    created_at: '2026-10-24T07:02:00Z',
  }),
  ...INBOX_ROWS.slice(3),
  ...MANY_TITLES.slice(1).map((title, i) =>
    notificationFixture({
      id: 40 + i,
      kind: i % 2 === 0 ? 'decision' : 'mention',
      actor: i % 3 === 0 ? SAM : DANA,
      item_id: 900 + i,
      item_key: `CP-${String(900 + i)}`,
      item_title: title,
      detail:
        i % 2 === 0
          ? { kind: 'decision', outcome: i % 4 === 0 ? 'approved_with_edits' : 'approved' }
          : { kind: 'mention', comment_id: 500 + i, version_n: 1 },
      created_at: new Date(Date.UTC(2026, 9, 19 - i, 14, 0)).toISOString(),
      read_at: new Date(Date.UTC(2026, 9, 19 - i, 15, 0)).toISOString(),
    }),
  ),
];

export function pageOf(rows: NotificationOut[]): NotificationPageOut {
  return { rows, unread_count: rows.filter((row) => row.read_at === null).length };
}

export const EMPTY_PAGE: NotificationPageOut = { rows: [], unread_count: 0 };
