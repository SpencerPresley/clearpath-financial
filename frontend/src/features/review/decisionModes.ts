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

/** The request-changes reason starts from the accepted findings (decisions.md, Ergonomics). */
export function changesRequestedDraft(findings: readonly FindingOut[]): string {
  return findings
    .filter((finding) => finding.state === 'accepted')
    .map((finding) => (finding.quote ? `- ${finding.message} (“${finding.quote}”)` : `- ${finding.message}`))
    .join('\n');
}
