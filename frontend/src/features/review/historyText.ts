/*
 * One sentence per audit event for the History tab (the event log, rendered; product-spec "Review screen").
 * Payloads carry database ids; `versions` maps version id → n, `users` maps user id → name, and `findings` maps
 * finding id → its message, so no rule id, enum value or snake_case field name reaches the screen (spec §5.4).
 *
 * `EVENT_SENTENCES` is keyed by every event type in the generated history union: a new backend event type fails
 * typecheck here (and historyText.test.ts) instead of rendering its raw type.
 */
import type { ItemHistoryOut } from '../../api/generated/model';
import {
  ATTACHMENT_KIND_LABELS,
  DRIFT_RESULT_LABELS,
  OUTCOME_LABELS,
  REOPEN_REASON_LABELS,
  RISK_TIER_LABELS,
  formatDate,
  plural,
} from '../../ui/labels';

type Entry = ItemHistoryOut['entries'][number];
export type HistoryEventType = Entry['type'];

export interface HistoryLookups {
  versions: ReadonlyMap<number, number>;
  users: ReadonlyMap<number, string>;
  /** Finding id → message, for the versions loaded so far. */
  findings?: ReadonlyMap<number, string>;
}

const firstLine = (text: string) => text.split('\n')[0]?.trim() ?? '';

const MAX_QUOTED = 72;

/** A finding's message, quoted and kept to one short line. */
function quoted(message: string): string {
  const line = firstLine(message).replace(/\.$/, '');
  return `“${line.length > MAX_QUOTED ? `${line.slice(0, MAX_QUOTED - 1).trimEnd()}…` : line}”`;
}

/** Item fields a PATCH records (reviews.services: tags, notes). */
const FIELD_LABELS: Record<string, string> = { tags: 'tags', notes: 'notes', monitored: 'monitoring' };
const fieldName = (field: string) => FIELD_LABELS[field] ?? field.replaceAll('_', ' ');

/** The drift fetch's failure codes that have a plainer reading than "couldn't be fetched". */
const DRIFT_FAILURES: Record<string, string> = {
  timeout: 'the page took too long to load',
  no_approved_version: 'there was no approved version to compare',
};

type Sentences = {
  [K in HistoryEventType]: (entry: Extract<Entry, { type: K }>, h: Helpers) => string;
};

interface Helpers {
  v: (versionId: number) => string;
  who: (userId: number | null) => string;
  finding: (findingId: number) => string;
}

export const EVENT_SENTENCES: Sentences = {
  'item.submitted': (e) => `Submitted v${String(e.payload.version_n)}`,
  'item.resubmitted': (e) => `Resubmitted v${String(e.payload.version_n)} (round ${String(e.payload.round)})`,
  'item.new_round_started': (e) =>
    `Started round ${String(e.payload.round)} with v${String(e.payload.version_n)}`,
  'item.assigned': (e, { who }) => {
    const reason = e.payload.reason === '' ? '' : ` · ${e.payload.reason}`;
    return e.payload.assignee_id === null
      ? `Unassigned${reason}`
      : `Assigned to ${who(e.payload.assignee_id)}${reason}`;
  },
  'item.review_started': () => 'Started review',
  'item.fields_updated': (e) => `Updated ${e.payload.changes.map((c) => fieldName(c.field)).join(', ')}`,
  'item.risk_tier_overridden': (e) =>
    `Risk tier changed from ${RISK_TIER_LABELS[e.payload.before]} to ${RISK_TIER_LABELS[e.payload.after]}`,
  'item.reopened': (e) => {
    const failed = e.payload.failed_snapshot_ids ?? [];
    const why =
      failed.length > 0
        ? ` (page couldn’t be fetched on ${plural(failed.length, 'daily check')} in a row)`
        : '';
    return `Sent to re-review: ${REOPEN_REASON_LABELS[e.payload.reason]}${why}`;
  },
  'item.expired': (e) => `Expired: ${REOPEN_REASON_LABELS[e.payload.reason]}`,
  'item.approval_expiring': (e) => `Approval expires soon (${formatDate(e.payload.expires_at)})`,
  'item.withdrawn': (e) => `Withdrawn: ${firstLine(e.payload.reason)}`,
  'item.imported': (e) => `Imported from the legacy tracker (${e.payload.legacy_ref})`,
  'version.created': (e) => `Created v${String(e.payload.version_n)}`,
  'checks.completed': (e, { v }) =>
    `${e.payload.source === 'llm' ? 'AI' : 'Code'} checks on ${v(e.payload.version_id)}: ${plural(e.payload.findings_count, 'finding')}`,
  'llm_check.requested': (e, { v }) => `AI check requested on ${v(e.payload.version_id)}`,
  'llm_check.started': (e, { v }) =>
    e.payload.attempt > 1
      ? `AI check started on ${v(e.payload.version_id)} (try ${String(e.payload.attempt)})`
      : `AI check started on ${v(e.payload.version_id)}`,
  'llm_check.retry_scheduled': (e, { v }) => `AI check on ${v(e.payload.version_id)} will try again`,
  'llm_check.succeeded': (e, { v }) =>
    `AI check finished on ${v(e.payload.version_id)} · ${plural(e.payload.findings_count, 'suggestion')}`,
  'llm_check.failed': (e, { v }) => `AI check failed on ${v(e.payload.version_id)}`,
  'finding.accepted': (e, { v, finding }) =>
    `Accepted ${finding(e.payload.finding_id)} on ${v(e.payload.version_id)}`,
  'finding.dismissed': (e, { v, finding }) =>
    e.payload.carried
      ? `Dismissal of ${finding(e.payload.finding_id)} carried to ${v(e.payload.version_id)}: ${e.payload.reason}`
      : `Dismissed ${finding(e.payload.finding_id)} on ${v(e.payload.version_id)}: ${e.payload.reason}`,
  'finding.reopened': (e, { v, finding }) =>
    `Reopened ${finding(e.payload.finding_id)} on ${v(e.payload.version_id)}`,
  'comment.added': (e, { v }) => `Commented on ${v(e.payload.version_id)}`,
  'decision.recorded': (e, { v }) => {
    const outcome = OUTCOME_LABELS[e.payload.outcome];
    const lane =
      e.payload.lane === 'standard'
        ? ''
        : e.payload.lane === 'fast_track'
          ? ' (fast-track)'
          : ' (reaffirmed)';
    const on = e.payload.outcome === 'changes_requested' || e.payload.outcome === 'rejected' ? ' on' : '';
    return `${outcome}${lane}${on} ${v(e.payload.version_id)}: ${firstLine(e.payload.reason)}`;
  },
  'placement.recorded': (e) => `Placement recorded: ${e.payload.location}`,
  'placement.updated': (e) =>
    e.payload.changes.length === 0
      ? 'Placement updated'
      : `Placement updated: ${e.payload.changes.map((c) => fieldName(c.field)).join(', ')}`,
  'placement.takedown_requested': (e) => `Takedown requested: ${firstLine(e.payload.reason)}`,
  'placement.takedown_confirmed': () => 'Takedown confirmed',
  'placement.drift_check_requested': (e) =>
    e.payload.trigger === 'manual' ? 'Placement check requested' : 'Daily placement check started',
  'placement.drift_checked': (e, { v }) => {
    if (e.payload.status === 'failed') {
      const why = DRIFT_FAILURES[e.payload.error_code ?? ''] ?? 'the page couldn’t be fetched';
      return `Placement check failed: ${why}`;
    }
    const compared = e.payload.compared_version_id;
    const against = compared === undefined || compared === null ? '' : ` against ${v(compared)}`;
    const result = e.payload.result ?? 'missing';
    return `Placement checked${against}: ${DRIFT_RESULT_LABELS[result]}`;
  },
  'placement.page_findings_flagged': (e) =>
    `Placement checked: ${DRIFT_RESULT_LABELS.unchanged}, ${plural(e.payload.rule_ids.length, 'new blocking finding')} beside it`,
  'attachment.added': (e) => `Evidence added: ${ATTACHMENT_KIND_LABELS[e.payload.kind]}`,
  'terms.published': (e) => `Offer terms v${String(e.payload.version)} published`,
  // Events about other entities; the item history doesn't normally carry them, but every type has a sentence.
  'partner.created': (e) => `Partner added: ${e.payload.name}`,
  'partner.updated': () => 'Partner updated',
  'user.availability_changed': (e, { who }) =>
    `${who(e.payload.user_id)} is ${e.payload.is_available ? 'available' : 'away'}`,
  'user.created': (e) => `Account created for ${e.payload.email}`,
  'user.roles_changed': (e, { who }) => `Roles changed for ${who(e.payload.user_id)}`,
  'user.active_changed': (e, { who }) =>
    `${who(e.payload.user_id)} ${e.payload.is_active ? 'reactivated' : 'deactivated'}`,
  'import.committed': (e) => `Import committed: ${plural(e.payload.created_count, 'item')}`,
  'export.created': (e) => `Export created: ${plural(e.payload.item_count, 'item')}`,
  'email.sent': (e) => `Email sent: ${e.payload.subject}`,
  'demo.reset': () => 'Demo reset',
};

export function describeEvent(entry: Entry, { versions, users, findings }: HistoryLookups): string {
  const helpers: Helpers = {
    v: (versionId) => {
      const n = versions.get(versionId);
      return n === undefined ? 'a version' : `v${String(n)}`;
    },
    who: (userId) => (userId === null ? 'nobody' : (users.get(userId) ?? 'a reviewer')),
    finding: (findingId) => {
      const message = findings?.get(findingId);
      return message === undefined ? 'a finding' : quoted(message);
    },
  };
  const sentence = EVENT_SENTENCES[entry.type] as (e: Entry, h: Helpers) => string;
  return sentence(entry, helpers);
}
