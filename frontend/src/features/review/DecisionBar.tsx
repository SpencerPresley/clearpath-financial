import { useQueryClient } from '@tanstack/react-query';

import { getGetItemDriftQueryKey, useCheckPlacementDrift } from '../../api/generated/drift/drift';
import { getGetItemHistoryQueryKey, getGetItemQueryKey, useClaimItem } from '../../api/generated/items/items';
import type { ItemDetailOut } from '../../api/generated/model';
import { RiskTierBadge, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
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
}

function LatestDecision({ item }: { item: ItemDetailOut }) {
  const decision = item.latest_decision;
  if (decision === null) {
    return null;
  }
  // A pulled or expired item's last decision is history, not its state ("Withdrawn" beside "Approved v2").
  const past = item.status === 'withdrawn' || item.status === 'expired';
  const outcome = OUTCOME_LABELS[decision.outcome];
  return (
    <span className="app-decision-summary">
      {past ? `Was ${outcome.toLowerCase()}` : outcome} v{decision.version_n} by {decision.approver.name}{' '}
      <RelativeAge at={decision.decided_at} />
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
        <h1 className="app-decision-bar-title" title={item.title}>
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
