import type { FindingOut, ItemDetailOut } from '../../api/generated/model';

/** The decision the inline panel is collecting a reason for. */
export type DecisionMode =
  'approved' | 'approved_with_edits' | 'changes_requested' | 'rejected' | 'fast_track' | 'reaffirm' | 'pull';

export const APPROVE_MODES: readonly DecisionMode[] = ['approved', 'approved_with_edits'];

/** A live page shows something other than the approved copy (`drift_rereview.restored` false), whatever the
 * reopen reason: the backend refuses Fast-track and Reaffirm then (409 drift_not_restored). */
export function liveCopyDiffers(item: ItemDetailOut): boolean {
  return item.drift_rereview?.restored === false;
}

/**
 * Fast-track is available when offer terms changed under a live approval and the system generated a
 * version with the new numbers (origin fast_track) newer than the approved one (spec §4.2 ruling 4), and the
 * live page shows the approved copy: fast-track is for "only the numbers changed", never a way to clear drift.
 */
export function fastTrackAvailable(item: ItemDetailOut): boolean {
  const approvedN = item.latest_decision?.version_n;
  return (
    item.status === 'needs_rereview' &&
    item.current_version?.origin === 'fast_track' &&
    approvedN !== undefined &&
    (item.current_version_n ?? 0) > approvedN &&
    !liveCopyDiffers(item)
  );
}

export type RereviewAction = 'fast_track' | 'reaffirm' | 'review' | 'check_now' | 'pull';

/**
 * What a reviewer can do with a re-review (reviews/decisions.py `reaffirm`, `_require_fast_trackable`).
 *
 * While a live page differs from the approved copy, for any reopen reason: Check now (once the partner fixes
 * it) or Pull. Nothing re-approves content that isn't what's live.
 *
 * Otherwise Fast-track when a version was generated with the new numbers. Reaffirm re-approves the approved
 * version after re-running code checks against today's terms, so it's offered only when that version is still
 * current, and never after a terms change (the approved version quotes the superseded numbers). Terms changes
 * with no generated version take the normal lane (`review`: claim → in_review). Pull always.
 */
export function rereviewActions(item: ItemDetailOut): RereviewAction[] {
  if (item.status !== 'needs_rereview') {
    return [];
  }
  if (liveCopyDiffers(item)) {
    return ['check_now', 'pull'];
  }
  const fastTrack = fastTrackAvailable(item);
  const approvedIsCurrent = item.latest_decision?.version_n === item.current_version_n;
  const reaffirm = item.reopen_reason !== 'terms_changed' && approvedIsCurrent;
  const actions: RereviewAction[] = [];
  if (fastTrack) actions.push('fast_track');
  if (reaffirm) actions.push('reaffirm');
  if (!fastTrack && !reaffirm) actions.push('review');
  actions.push('pull');
  return actions;
}

/** The request-changes reason starts from the accepted findings (decisions.md, Ergonomics). */
export function changesRequestedDraft(findings: readonly FindingOut[]): string {
  return findings
    .filter((finding) => finding.state === 'accepted')
    .map((finding) => (finding.quote ? `- ${finding.message} (“${finding.quote}”)` : `- ${finding.message}`))
    .join('\n');
}
