import type { FindingOut, ItemDetailOut } from '../../api/generated/model';

/** The decision the inline panel is collecting a reason for. */
export type DecisionMode =
  'approved' | 'approved_with_edits' | 'changes_requested' | 'rejected' | 'fast_track' | 'reaffirm' | 'pull';

export const APPROVE_MODES: readonly DecisionMode[] = ['approved', 'approved_with_edits'];

/**
 * Fast-track is available when offer terms changed under a live approval and the system generated a
 * version with the new numbers (origin fast_track) newer than the approved one (spec §4.2 ruling 4).
 */
export function fastTrackAvailable(item: ItemDetailOut): boolean {
  const approvedN = item.latest_decision?.version_n;
  return (
    item.status === 'needs_rereview' &&
    item.current_version?.origin === 'fast_track' &&
    approvedN !== undefined &&
    (item.current_version_n ?? 0) > approvedN
  );
}

export type RereviewAction = 'fast_track' | 'reaffirm' | 'review' | 'pull';

/**
 * What a reviewer can do with a re-review, by why it reopened. Reaffirm re-approves the approved version
 * after re-running code checks against today's terms (reviews/decisions.py `reaffirm`), so after a terms
 * change it can only be refused: the approved version quotes the superseded numbers, and once a fast-track
 * version exists it isn't even current. Terms changes therefore get Fast-track (a version was generated with
 * the new numbers) or the normal lane (`review`: claim → in_review) when none could be; Pull always.
 */
export function rereviewActions(item: ItemDetailOut): RereviewAction[] {
  if (item.status !== 'needs_rereview') {
    return [];
  }
  if (item.reopen_reason === 'terms_changed') {
    return fastTrackAvailable(item) ? ['fast_track', 'pull'] : ['review', 'pull'];
  }
  return fastTrackAvailable(item) ? ['fast_track', 'reaffirm', 'pull'] : ['reaffirm', 'pull'];
}

/** The request-changes reason starts from the accepted findings (decisions.md, Ergonomics). */
export function changesRequestedDraft(findings: readonly FindingOut[]): string {
  return findings
    .filter((finding) => finding.state === 'accepted')
    .map((finding) => (finding.quote ? `- ${finding.message} (“${finding.quote}”)` : `- ${finding.message}`))
    .join('\n');
}
