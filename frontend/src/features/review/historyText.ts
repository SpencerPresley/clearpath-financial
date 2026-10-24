/*
 * One sentence per audit event for the History tab (the event log, rendered; product-spec "Review screen").
 * Payloads carry database ids; `versions` maps version id → n and `users` maps user id → name.
 */
import type { ItemHistoryOut } from '../../api/generated/model';
import { OUTCOME_LABELS, REOPEN_REASON_LABELS, plural } from '../../ui/labels';

type Entry = ItemHistoryOut['entries'][number];

export interface HistoryLookups {
  versions: ReadonlyMap<number, number>;
  users: ReadonlyMap<number, string>;
}

const firstLine = (text: string) => text.split('\n')[0]?.trim() ?? '';

export function describeEvent(entry: Entry, { versions, users }: HistoryLookups): string {
  const v = (versionId: number) => {
    const n = versions.get(versionId);
    return n === undefined ? 'a version' : `v${String(n)}`;
  };
  const who = (userId: number | null) => (userId === null ? 'nobody' : (users.get(userId) ?? 'a reviewer'));

  switch (entry.type) {
    case 'item.submitted':
      return `Submitted v${String(entry.payload.version_n)}`;
    case 'item.resubmitted':
      return `Resubmitted v${String(entry.payload.version_n)} (round ${String(entry.payload.round)})`;
    case 'item.new_round_started':
      return `Started round ${String(entry.payload.round)} with v${String(entry.payload.version_n)}`;
    case 'item.assigned': {
      const reason = entry.payload.reason === '' ? '' : ` · ${entry.payload.reason}`;
      return entry.payload.assignee_id === null
        ? `Unassigned${reason}`
        : `Assigned to ${who(entry.payload.assignee_id)}${reason}`;
    }
    case 'item.review_started':
      return 'Started review';
    case 'item.fields_updated':
      return `Updated ${entry.payload.changes.map((c) => c.field).join(', ')}`;
    case 'item.risk_tier_overridden':
      return `Risk tier changed from ${entry.payload.before} to ${entry.payload.after}`;
    case 'item.reopened': {
      const failed = entry.payload.failed_snapshot_ids ?? [];
      const why =
        failed.length > 0 ? ` (page couldn’t be fetched on ${plural(failed.length, 'check')} in a row)` : '';
      return `Sent to re-review: ${REOPEN_REASON_LABELS[entry.payload.reason]}${why}`;
    }
    case 'item.expired':
      return `Expired: ${REOPEN_REASON_LABELS[entry.payload.reason]}`;
    case 'item.withdrawn':
      return `Withdrawn: ${firstLine(entry.payload.reason)}`;
    case 'item.imported':
      return `Imported from the legacy tracker (${entry.payload.legacy_ref})`;
    case 'version.created':
      return `Created v${String(entry.payload.version_n)}`;
    case 'checks.completed':
      return `${entry.payload.source === 'llm' ? 'AI' : 'Code'} checks on ${v(entry.payload.version_id)}: ${plural(entry.payload.findings_count, 'finding')}`;
    case 'llm_check.requested':
      return `AI check requested on ${v(entry.payload.version_id)}`;
    case 'llm_check.succeeded':
      return `AI check finished on ${v(entry.payload.version_id)} · ${plural(entry.payload.findings_count, 'suggestion')}`;
    case 'llm_check.failed':
      return `AI check failed on ${v(entry.payload.version_id)}`;
    case 'finding.accepted':
      return `Accepted ${entry.payload.rule_id} on ${v(entry.payload.version_id)}`;
    case 'finding.dismissed':
      return entry.payload.carried
        ? `Dismissal of ${entry.payload.rule_id} carried to ${v(entry.payload.version_id)}: ${entry.payload.reason}`
        : `Dismissed ${entry.payload.rule_id} on ${v(entry.payload.version_id)}: ${entry.payload.reason}`;
    case 'finding.reopened':
      return `Reopened ${entry.payload.rule_id} on ${v(entry.payload.version_id)}`;
    case 'comment.added':
      return `Commented on ${v(entry.payload.version_id)}`;
    case 'decision.recorded': {
      const outcome = OUTCOME_LABELS[entry.payload.outcome];
      const lane =
        entry.payload.lane === 'standard'
          ? ''
          : entry.payload.lane === 'fast_track'
            ? ' (fast-track)'
            : ' (reaffirmed)';
      const on =
        entry.payload.outcome === 'changes_requested' || entry.payload.outcome === 'rejected' ? ' on' : '';
      return `${outcome}${lane}${on} ${v(entry.payload.version_id)}: ${firstLine(entry.payload.reason)}`;
    }
    case 'placement.recorded':
      return `Placement recorded: ${entry.payload.location}`;
    case 'placement.updated':
      return 'Placement updated';
    case 'placement.takedown_requested':
      return `Takedown requested: ${firstLine(entry.payload.reason)}`;
    case 'placement.takedown_confirmed':
      return 'Takedown confirmed';
    case 'placement.drift_check_requested':
      return entry.payload.trigger === 'manual'
        ? 'Placement check requested'
        : 'Daily placement check started';
    case 'placement.drift_checked': {
      if (entry.payload.status === 'failed') {
        const why = entry.payload.error_code ?? '';
        return why === '' ? 'Placement check failed' : `Placement check failed (${why.replaceAll('_', ' ')})`;
      }
      const compared = entry.payload.compared_version_id;
      const against = compared === undefined || compared === null ? '' : ` against ${v(compared)}`;
      if (entry.payload.result === 'unchanged') return `Placement checked${against}: copy unchanged`;
      if (entry.payload.result === 'modified') return `Placement checked${against}: copy changed on the page`;
      return `Placement checked${against}: approved copy missing from the page`;
    }
    case 'placement.page_findings_flagged':
      return `Placement checked: copy unchanged, ${plural(entry.payload.rule_ids.length, 'new blocking finding')} beside it`;
    case 'attachment.added':
      return 'Evidence added';
    case 'terms.published':
      return `Offer terms v${String(entry.payload.version)} published`;
    default:
      return entry.type;
  }
}
