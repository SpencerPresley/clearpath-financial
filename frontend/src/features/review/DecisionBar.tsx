import type { ItemDetailOut } from '../../api/generated/model';
import { RiskTierBadge, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
import { OUTCOME_LABELS, formatDate } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { fastTrackAvailable } from './decisionModes';
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
}

function LatestDecision({ item }: { item: ItemDetailOut }) {
  const decision = item.latest_decision;
  if (decision === null) {
    return null;
  }
  return (
    <span className="app-decision-summary">
      {OUTCOME_LABELS[decision.outcome]} v{decision.version_n} by {decision.approver.name}{' '}
      <RelativeAge at={decision.decided_at} />
      {decision.expires_at !== null && item.status === 'approved' && (
        <> · expires {formatDate(decision.expires_at)}</>
      )}
    </span>
  );
}

/**
 * The sticky bar (spec §5.3): which item, its state, and the decisions. Approve stays visible but disabled
 * with the reason beside it, so "why can't I approve" is never a mystery.
 */
export function DecisionBar({ item, gate, isDecider, mode, onMode, onShortcuts }: DecisionBarProps) {
  const pressed = (m: DecisionMode) => (mode === m ? true : undefined);
  const showDecisions = isDecider && gate.canDecide;
  const showRereview = isDecider && item.status === 'needs_rereview';

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
        {showDecisions && (
          <>
            {!gate.approve.enabled && (
              <span className="app-gate-note" id="approve-blockers">
                {gate.approve.blockers.join(' · ')}
              </span>
            )}
            {gate.approve.enabled && gate.overrideRequired && (
              <span className="app-gate-note">AI check failed · approving needs an override reason</span>
            )}
            <Button
              variant="primary"
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
            {fastTrackAvailable(item) && (
              <Button
                variant="primary"
                icon="action.approve"
                aria-pressed={pressed('fast_track')}
                onPress={() => {
                  onMode('fast_track');
                }}
              >
                Fast-track approve v{item.current_version_n}
              </Button>
            )}
            <Button
              icon="action.approve"
              aria-pressed={pressed('reaffirm')}
              onPress={() => {
                onMode('reaffirm');
              }}
            >
              Reaffirm
            </Button>
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
    </header>
  );
}
