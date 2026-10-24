/*
 * "What's waiting on me, and why" (product-spec, My submissions): which section an item sits in, the one
 * line that replaces an "any update?" email, and the marketer's next action when there is one.
 */
import type { ItemDetailOut, ItemRowOut, ItemStatus } from '../../api/generated/model';
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

/** Statuses whose why line needs the item detail (the decision behind it). */
export const NEEDS_DETAIL: ReadonlySet<ItemStatus> = new Set(['changes_requested']);

function firstLine(text: string): string {
  return (
    text
      .split('\n')
      .find((line) => line.trim() !== '')
      ?.trim() ?? ''
  );
}

/** `detail` is optional: rows render before (or without) it and fill in when it arrives. */
export function waitingOn(row: ItemRowOut, detail?: ItemDetailOut): WaitingOn {
  const assignee = row.assignee?.name;
  switch (row.status) {
    case 'changes_requested': {
      const decision = detail?.latest_decision;
      const reason = decision?.outcome === 'changes_requested' ? firstLine(decision.reason) : '';
      return {
        bucket: 'you',
        why:
          decision?.outcome === 'changes_requested'
            ? `Changes requested by ${decision.approver.name}${reason === '' ? '' : `: ${reason}`}`
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
      // ItemRowOut has no expiry; it shows only when the detail is at hand.
      const expires = detail?.approval_expires_at ?? detail?.latest_decision?.expires_at ?? null;
      return {
        bucket: 'approved',
        why: expires === null ? 'Approved' : `Approved · expires ${formatDate(expires)}`,
      };
    }
    case 'rejected':
      return { bucket: 'closed', why: 'Rejected' };
  }
}
