/*
 * "What's waiting on me, and why" (product-spec, My submissions): which section an item sits in, the one
 * line that replaces an "any update?" email, and the marketer's next action when there is one.
 */
import type { ItemRowOut } from '../../api/generated/model';
import { REOPEN_REASON_LABELS, formatDate } from '../../ui/labels';

export type WaitingBucket = 'you' | 'compliance' | 'approved' | 'closed';
export type MarketerAction = 'resubmit' | 'new_round';

export interface WaitingOn {
  bucket: WaitingBucket;
  why: string;
  action?: MarketerAction;
}

export const BUCKETS: readonly { id: WaitingBucket; label: string }[] = [
  { id: 'you', label: 'Waiting on you' },
  { id: 'compliance', label: 'With compliance' },
  { id: 'approved', label: 'Approved' },
  { id: 'closed', label: 'Closed' },
];

function firstLine(text: string): string {
  return (
    text
      .split('\n')
      .find((line) => line.trim() !== '')
      ?.trim() ?? ''
  );
}

/** Everything comes from the row (its latest decision and approval expiry), so the page makes one request. */
export function waitingOn(row: ItemRowOut): WaitingOn {
  const assignee = row.assignee?.name;
  switch (row.status) {
    case 'changes_requested': {
      const decision = row.latest_decision;
      const reason = decision?.outcome === 'changes_requested' ? firstLine(decision.reason) : '';
      return {
        bucket: 'you',
        why:
          decision?.outcome === 'changes_requested'
            ? reason === ''
              ? `Changes requested by ${decision.approver.name}`
              : `${decision.approver.name}: ${reason}`
            : 'Changes requested',
        action: 'resubmit',
      };
    }
    case 'withdrawn':
      return {
        bucket: 'you',
        why: 'Pulled. Start a new round when the copy is fixed.',
        action: 'new_round',
      };
    case 'expired':
      return {
        bucket: 'you',
        why: 'Approval expired. Start a new round to run it again.',
        action: 'new_round',
      };
    case 'draft':
      return { bucket: 'you', why: 'Not submitted yet' };
    case 'submitted':
      return {
        bucket: 'compliance',
        why: assignee === undefined ? 'Waiting for a reviewer' : `With ${assignee}`,
      };
    case 'in_review':
      return { bucket: 'compliance', why: assignee === undefined ? 'In review' : `${assignee} is reviewing` };
    case 'needs_rereview':
      return {
        bucket: 'compliance',
        why:
          row.reopen_reason === null
            ? 'Back in review'
            : `Back in review: ${REOPEN_REASON_LABELS[row.reopen_reason]}`,
      };
    case 'approved': {
      // Approved, so this is the expiry of the approval in force.
      const expires = row.approval_expires_at;
      return {
        bucket: 'approved',
        why: expires === null ? 'Approved' : `Approved · expires ${formatDate(expires)}`,
      };
    }
    case 'rejected':
      return { bucket: 'closed', why: 'Rejected' };
  }
}
