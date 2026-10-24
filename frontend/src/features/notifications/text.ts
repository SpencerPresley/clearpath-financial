/*
 * One line per notification, in domain language: "Dana Reyes requested changes on CP-42 · Fall personal loan
 * promo". Built from the row's actor, item and event detail; the stored `message` is the fallback for rows the
 * API can't detail (no event, or an event type this file doesn't phrase).
 *
 * The line is split around the item so the inbox can truncate only the title: whatever comes after the item
 * ("with edits", a re-review reason, an expiry date) stays visible.
 */
import type { AssignmentMode, DecisionOutcome, NotificationOut } from '../../api/generated/model';
import type { IconKey } from '../../ui/icons';
import { REOPEN_REASON_LABELS } from '../../ui/labels';

export type Tone = 'success' | 'warning' | 'error' | 'alert';

export interface NotificationText {
  icon: IconKey;
  /** Status tone for the icon when the row reports a status (a decision, a re-review); otherwise muted. */
  tone: Tone | undefined;
  before: string;
  item: { key: string; title: string } | null;
  after: string;
  /** The whole line as plain text: the row's accessible name and tooltip. */
  text: string;
}

/**
 * Glyph per kind. Keyed by string, not `Record<NotificationKind, …>`, so a kind added on the backend (the drift
 * monitor's page findings) renders before the client is regenerated; text.test.ts checks every generated kind.
 */
export const KIND_ICONS: Readonly<Record<string, IconKey>> = {
  assignment: 'action.assign',
  decision: 'entity.decision',
  rereview: 'status.needs_rereview',
  mention: 'notify.mention',
  expiry_warning: 'notify.expiring',
  page_findings: 'severity.blocking',
};

const KIND_TONES: Readonly<Record<string, Tone>> = {
  rereview: 'alert',
  page_findings: 'error',
};

const OUTCOME_ICONS: Record<DecisionOutcome, { icon: IconKey; tone: Tone }> = {
  approved: { icon: 'status.approved', tone: 'success' },
  approved_with_edits: { icon: 'status.approved', tone: 'success' },
  changes_requested: { icon: 'status.changes_requested', tone: 'warning' },
  rejected: { icon: 'status.rejected', tone: 'error' },
};

// [before the item, after it], given who acted.
const OUTCOME_WORDS: Record<DecisionOutcome, (actor: string) => [string, string]> = {
  approved: (actor) => [`${actor} approved `, ''],
  approved_with_edits: (actor) => [`${actor} approved `, ' with edits'],
  changes_requested: (actor) => [`${actor} requested changes on `, ''],
  rejected: (actor) => [`${actor} rejected `, ''],
};

const OUTCOME_WITHOUT_ACTOR: Record<DecisionOutcome, [string, string]> = {
  approved: ['Approved: ', ''],
  approved_with_edits: ['Approved with edits: ', ''],
  changes_requested: ['Changes requested on ', ''],
  rejected: ['Rejected: ', ''],
};

function assignmentWords(mode: AssignmentMode, actor: string | null): [string, string] {
  switch (mode) {
    case 'pool':
      return ['', ' is in the unassigned pool'];
    case 'sticky':
      return ['', ' is back for your review'];
    case 'manual':
      return actor === null ? ['', ' was assigned to you'] : [`${actor} assigned `, ' to you'];
    case 'handoff':
      return actor === null ? ['', ' was handed to you'] : [`${actor} handed `, ' to you'];
    case 'lowest_load':
    case 'claim':
      return ['', ' was assigned to you'];
  }
}

const expiryFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });

/** [before, after] around the item, or null when only the stored message can say it. */
function words(n: NotificationOut): [string, string] | null {
  const actor = n.actor?.name ?? null;
  const detail = n.detail;
  switch (n.kind) {
    case 'decision':
      if (detail?.kind !== 'decision') return null;
      return actor === null ? OUTCOME_WITHOUT_ACTOR[detail.outcome] : OUTCOME_WORDS[detail.outcome](actor);
    case 'assignment':
      return detail?.kind === 'assignment' ? assignmentWords(detail.mode, actor) : null;
    case 'mention':
      return actor === null ? ['You were mentioned on ', ''] : [`${actor} mentioned you on `, ''];
    case 'rereview':
      return detail?.kind === 'rereview'
        ? ['', ` needs re-review · ${REOPEN_REASON_LABELS[detail.reason].toLowerCase()}`]
        : ['', ' needs re-review'];
    case 'expiry_warning':
      return detail?.kind === 'expiry_warning'
        ? ['Approval for ', ` expires ${expiryFormat.format(new Date(detail.expires_at))}`]
        : null;
    default:
      // The drift monitor's alert (PR #40) needs nothing from the payload.
      return (n.kind as string) === 'page_findings'
        ? ['Partner page carrying ', ' has new blocking findings']
        : null;
  }
}

function iconFor(n: NotificationOut): { icon: IconKey; tone: Tone | undefined } {
  if (n.detail?.kind === 'decision') return OUTCOME_ICONS[n.detail.outcome];
  return { icon: KIND_ICONS[n.kind] ?? 'feedback.info', tone: KIND_TONES[n.kind] };
}

export function describeNotification(n: NotificationOut): NotificationText {
  const { icon, tone } = iconFor(n);
  const around = words(n);
  if (around === null || n.item_key === null || n.item_title === null) {
    return { icon, tone, before: n.message, item: null, after: '', text: n.message };
  }
  const [before, after] = around;
  const item = { key: n.item_key, title: n.item_title };
  return { icon, tone, before, item, after, text: `${before}${item.key} · ${item.title}${after}` };
}

export interface NotificationLink {
  itemId: string;
  search: { tab?: 'comments'; v?: number };
}

/** Where a row goes: the item's review screen; for a mention, its Comments tab on the comment's version. */
export function notificationLink(n: NotificationOut): NotificationLink | null {
  if (n.item_id === null) return null;
  const itemId = String(n.item_id);
  if (n.kind !== 'mention') return { itemId, search: {} };
  return n.detail?.kind === 'mention'
    ? { itemId, search: { tab: 'comments', v: n.detail.version_n } }
    : { itemId, search: { tab: 'comments' } };
}
