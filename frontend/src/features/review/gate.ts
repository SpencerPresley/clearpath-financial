/*
 * What the reviewer may decide right now (spec §4.2 ruling 3). The server enforces the same rules
 * (OpenFindingsBlockDecision, AiCheckPending); this is the plain explanation shown before they hit it.
 */
import type { CheckStatus, FindingOut, ItemStatus } from '../../api/generated/model';
import { plural } from '../../ui/labels';

export interface GateInput {
  status: ItemStatus;
  llm_check_status: CheckStatus;
  current_version_n: number | null;
}

export interface DecisionGate {
  /** Decisions apply to submitted / in-review items, on the current version. */
  canDecide: boolean;
  /** Approve and Approve with edits; Request changes and Reject only need canDecide. */
  approve: { enabled: boolean; blockers: string[] };
  /** The AI check failed: approving needs a recorded override reason. */
  overrideRequired: boolean;
  openCount: number;
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

  const blockers: string[] = [];
  if (!viewingCurrent) {
    blockers.push(`Viewing v${String(shownVersionN)} · decisions apply to v${String(current)}`);
  } else {
    if (openCount > 0) {
      blockers.push(`${plural(openCount, 'finding')} to triage`);
    }
    if (item.llm_check_status === 'pending') {
      blockers.push('AI check queued');
    } else if (item.llm_check_status === 'running') {
      blockers.push('AI check running');
    }
  }

  const canDecide = DECIDABLE.includes(item.status) && viewingCurrent;
  return {
    canDecide,
    approve: { enabled: canDecide && blockers.length === 0, blockers },
    overrideRequired: item.llm_check_status === 'failed',
    openCount,
  };
}
