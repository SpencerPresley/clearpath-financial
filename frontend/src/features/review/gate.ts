/*
 * What the reviewer may decide right now (spec §4.2 ruling 3). The server enforces the same rules
 * (open_findings_block_decision, accepted_findings_block_approval, ai_check_pending); this is the plain
 * explanation shown before they hit one.
 *
 * Accepted means "this must change", and the approved version is exactly what goes live, so a plain
 * Approve also needs zero accepted findings; Approve with edits is how the reviewer makes those changes.
 */
import type { CheckStatus, FindingOut, ItemStatus } from '../../api/generated/model';
import { plural } from '../../ui/labels';

export interface GateInput {
  status: ItemStatus;
  llm_check_status: CheckStatus;
  current_version_n: number | null;
}

export interface ActionGate {
  enabled: boolean;
  /** Plain-language reasons it's disabled, e.g. "2 findings to triage". */
  blockers: string[];
}

export interface DecisionGate {
  /** Decisions apply to submitted / in-review items, on the current version. */
  canDecide: boolean;
  approve: ActionGate;
  approveWithEdits: ActionGate;
  /** The AI check failed: approving needs a recorded override reason. */
  overrideRequired: boolean;
  openCount: number;
  acceptedCount: number;
}

const DECIDABLE: readonly ItemStatus[] = ['submitted', 'in_review'];

export function decisionGate(
  item: GateInput,
  findings: readonly Pick<FindingOut, 'state'>[],
  shownVersionN: number,
): DecisionGate {
  const current = item.current_version_n;
  const viewingCurrent = current === null || shownVersionN === current;
  const openCount = findings.filter((finding) => finding.state === 'open').length;
  const acceptedCount = findings.filter((finding) => finding.state === 'accepted').length;

  const shared: string[] = [];
  if (!viewingCurrent) {
    shared.push(`Viewing v${String(shownVersionN)} · decisions apply to v${String(current)}`);
  } else {
    if (openCount > 0) {
      shared.push(`${plural(openCount, 'finding')} to triage`);
    }
    if (item.llm_check_status === 'pending') {
      shared.push('AI check queued');
    } else if (item.llm_check_status === 'running') {
      shared.push('AI check running');
    }
  }
  const approveOnly =
    viewingCurrent && acceptedCount > 0
      ? [`${plural(acceptedCount, 'accepted finding')} ${acceptedCount === 1 ? 'needs' : 'need'} a change`]
      : [];

  const canDecide = DECIDABLE.includes(item.status) && viewingCurrent;
  const approveBlockers = [...shared, ...approveOnly];
  return {
    canDecide,
    approve: { enabled: canDecide && approveBlockers.length === 0, blockers: approveBlockers },
    approveWithEdits: { enabled: canDecide && shared.length === 0, blockers: shared },
    overrideRequired: item.llm_check_status === 'failed',
    openCount,
    acceptedCount,
  };
}
