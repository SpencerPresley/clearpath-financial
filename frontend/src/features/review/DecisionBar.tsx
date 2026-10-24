import { useQueryClient } from '@tanstack/react-query';

import { getGetItemDriftQueryKey, useCheckPlacementDrift } from '../../api/generated/drift/drift';
import { getGetItemHistoryQueryKey, getGetItemQueryKey, useClaimItem } from '../../api/generated/items/items';
import type { DecisionOutcome, ItemDetailOut, ItemStatus } from '../../api/generated/model';
import { RiskTierBadge, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
import { Kbd } from '../../ui/Kbd';
import { OUTCOME_LABELS, formatDate } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { showToast } from '../../ui/toast';
import { rereviewActions } from './decisionModes';
import type { DecisionMode } from './decisionModes';
import type { DecisionGate } from './gate';

export interface DecisionBarProps {
  item: ItemDetailOut;
  gate: DecisionGate;
  /** Reviewer or lead: the only roles that decide (spec §4.3). */
  isDecider: boolean;
  mode: DecisionMode | null;
  onMode: (mode: DecisionMode) => void;
  onShortcuts: () => void;
  /** A drift re-review's Check now was queued: show where the result lands (the Details tab's placements). */
  onCheckQueued: () => void;
  /** The next row of the reviewer's queue view (j). */
  onNextItem: () => void;
  nextPending: boolean;
}

/** Focus targets after a decision: the Next item button, else the title. */
export const NEXT_ITEM_ID = 'review-next-item';
export const REVIEW_TITLE_ID = 'review-title';

/** The status a decision leaves the item in; any other status means the item has moved on since. */
const DECIDED_STATUS: Record<DecisionOutcome, ItemStatus> = {
  approved: 'approved',
  approved_with_edits: 'approved',
  changes_requested: 'changes_requested',
  rejected: 'rejected',
};

/**
 * The latest decision, worded by whether it's still the item's state. Once the item has moved on it reads as
 * history, so the header never shows two current states ("Submitted" beside "Changes requested v2"): after a
 * resubmission or a new round it's the last round's outcome; after a pull, an expiry or a reopen it's what
 * the item was.
 */
export function latestDecisionText(item: ItemDetailOut): string | null {
  const decision = item.latest_decision;
  if (decision === null) return null;
  const outcome = OUTCOME_LABELS[decision.outcome];
  const n = `v${String(decision.version_n)}`;
  if (item.status === DECIDED_STATUS[decision.outcome]) return `${outcome} ${n} by ${decision.approver.name}`;
  if (item.status === 'submitted' || item.status === 'in_review') {
    return `Last round: ${outcome.toLowerCase()} on ${n} by ${decision.approver.name}`;
  }
  return `Was ${outcome.toLowerCase()} ${n} by ${decision.approver.name}`;
}

function LatestDecision({ item }: { item: ItemDetailOut }) {
  const decision = item.latest_decision;
  const text = latestDecisionText(item);
  if (decision === null || text === null) {
    return null;
  }
  return (
    <span className="app-decision-summary">
      {text} <RelativeAge at={decision.decided_at} />
      {decision.expires_at !== null && item.status === 'approved' && (
        <> · expires {formatDate(decision.expires_at)}</>
      )}
    </span>
  );
}

/** Why Approve is off, and the way forward when only accepted findings stand in the way. */
export function approveNote(gate: DecisionGate): string | null {
  if (gate.approve.enabled) {
    return gate.overrideRequired ? 'AI check failed · approving needs an override reason' : null;
  }
  const why = gate.approve.blockers.join(' · ');
  return gate.approveWithEdits.enabled ? `${why} · Approve with edits or Request changes` : why;
}

/**
 * The sticky bar (spec §5.3): which item, its state, and the decisions. Approve stays visible but disabled
 * with the reason under the buttons, so "why can't I approve" is never a mystery.
 */
export function DecisionBar({
  item,
  gate,
  isDecider,
  mode,
  onMode,
  onShortcuts,
  onCheckQueued,
  onNextItem,
  nextPending,
}: DecisionBarProps) {
  const pressed = (m: DecisionMode) => (mode === m ? true : undefined);
  const showDecisions = isDecider && gate.canDecide;
  const rereview = isDecider ? rereviewActions(item) : [];
  const showRereview = rereview.length > 0;
  const note = showDecisions ? approveNote(gate) : null;
  const approvedN = item.latest_decision?.version_n;
  // Only the assignee (or a lead) may decide; an unassigned item is claimed first (decisions.md, assignment).
  // A re-review that offers the normal lane claims through its Review button instead.
  const showClaim =
    isDecider &&
    item.assignee === null &&
    (item.status === 'submitted' || (item.status === 'needs_rereview' && !rereview.includes('review')));
  const queryClient = useQueryClient();
  const claim = useClaimItem({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getGetItemQueryKey(item.id) });
        void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(item.id) });
      },
      onError: (error) => {
        showToast({ title: 'Not claimed', description: apiErrorMessage(error), tone: 'error' });
      },
    },
  });
  // Drift re-review: re-check the placement that sent the item back. The Details tab polls until the check
  // lands and then refreshes the item, which is when Reaffirm appears (if the partner restored the copy).
  const driftPlacementId = item.drift_rereview?.placement_id;
  const checkNow = useCheckPlacementDrift({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getGetItemDriftQueryKey(item.id) });
        onCheckQueued();
      },
      onError: (error) => {
        showToast({ title: 'Not checked', description: apiErrorMessage(error), tone: 'error' });
      },
    },
  });

  return (
    <header className="app-decision-bar">
      <div className="app-decision-bar-heading">
        <h1 id={REVIEW_TITLE_ID} className="app-decision-bar-title" title={item.title} tabIndex={-1}>
          {item.title}
        </h1>
        <div className="app-decision-bar-meta">
          <ItemKey value={item.key} />
          <StatusBadge status={item.status} />
          <span className="app-decision-bar-risk">
            <RiskTierBadge tier={item.risk_tier} />
          </span>
          <span className="app-meta-text app-figure">
            Round {item.round} · v{item.current_version_n ?? '—'}
          </span>
        </div>
      </div>
      <div className="app-decision-bar-actions">
        <div className="app-decision-bar-buttons">
          {showClaim && (
            <Button
              icon="action.assign"
              isDisabled={claim.isPending}
              onPress={() => {
                claim.mutate({ itemId: item.id });
              }}
            >
              Claim
            </Button>
          )}
          {showDecisions && (
            <>
              <Button
                variant={mode === 'approved' ? 'secondary' : 'primary'}
                icon="action.approve"
                isDisabled={!gate.approve.enabled}
                aria-describedby={gate.approve.enabled ? undefined : 'approve-blockers'}
                aria-pressed={pressed('approved')}
                onPress={() => {
                  onMode('approved');
                }}
              >
                Approve
              </Button>
              <Button
                icon="action.edit"
                aria-pressed={pressed('approved_with_edits')}
                onPress={() => {
                  onMode('approved_with_edits');
                }}
              >
                Approve with edits
              </Button>
              <Button
                icon="action.request_changes"
                aria-pressed={pressed('changes_requested')}
                onPress={() => {
                  onMode('changes_requested');
                }}
              >
                Request changes
              </Button>
              <Button
                icon="action.reject"
                aria-pressed={pressed('rejected')}
                onPress={() => {
                  onMode('rejected');
                }}
              >
                Reject
              </Button>
            </>
          )}
          {showRereview && (
            <>
              {rereview.includes('fast_track') && (
                <Button
                  variant={mode === 'fast_track' ? 'secondary' : 'primary'}
                  icon="action.approve"
                  aria-pressed={pressed('fast_track')}
                  onPress={() => {
                    onMode('fast_track');
                  }}
                >
                  Fast-track approve v{item.current_version_n}
                </Button>
              )}
              {rereview.includes('review') && (
                <Button
                  variant="primary"
                  icon="action.assign"
                  isDisabled={claim.isPending}
                  onPress={() => {
                    claim.mutate({ itemId: item.id });
                  }}
                >
                  Review
                </Button>
              )}
              {rereview.includes('check_now') && driftPlacementId !== undefined && (
                <Button
                  variant="primary"
                  icon="action.reload"
                  isPending={checkNow.isPending}
                  onPress={() => {
                    checkNow.mutate({ placementId: driftPlacementId });
                  }}
                >
                  Check now
                </Button>
              )}
              {rereview.includes('reaffirm') && (
                <Button
                  icon="action.approve"
                  aria-pressed={pressed('reaffirm')}
                  onPress={() => {
                    onMode('reaffirm');
                  }}
                >
                  {approvedN === undefined ? 'Reaffirm' : `Reaffirm v${String(approvedN)}`}
                </Button>
              )}
              <Button
                icon="action.pull"
                aria-pressed={pressed('pull')}
                onPress={() => {
                  onMode('pull');
                }}
              >
                Pull
              </Button>
            </>
          )}
          {!showDecisions && !showRereview && <LatestDecision item={item} />}
          {isDecider && !showDecisions && !showRereview && (
            <Button id={NEXT_ITEM_ID} icon="action.open" isPending={nextPending} onPress={onNextItem}>
              Next item
              <span aria-hidden="true">
                <Kbd keys={['J']} />
              </span>
            </Button>
          )}
          <IconButton icon="action.shortcuts" aria-label="Keyboard shortcuts (?)" onPress={onShortcuts} />
        </div>
        {note !== null && (
          <p className="app-decision-bar-note" id="approve-blockers">
            {note}
          </p>
        )}
      </div>
    </header>
  );
}
