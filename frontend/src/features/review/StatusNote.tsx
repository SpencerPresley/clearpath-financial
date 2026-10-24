import { useListPlacements } from '../../api/generated/items/items';
import type { ItemDetailOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { REOPEN_REASON_LABELS, formatDate, plural } from '../../ui/labels';
import { fastTrackAvailable } from './decisionModes';

/**
 * One line above the copy when the item's state changes what the reviewer should do: re-review of live
 * content (alert), withdrawn (neutral), or an older version on screen.
 */
export function StatusNote({
  item,
  viewingCurrent,
  shownN,
  compareN,
  onShowCurrent,
  onCompareApproved,
}: {
  item: ItemDetailOut;
  viewingCurrent: boolean;
  shownN: number;
  compareN: number | undefined;
  onShowCurrent: () => void;
  onCompareApproved: (approvedN: number) => void;
}) {
  if (!viewingCurrent) {
    return (
      <div className="app-note" data-tone="neutral">
        <Icon name="entity.version" />
        <span>
          Viewing v{shownN}. Findings are read-only here; decisions apply to v{item.current_version_n}.
        </span>
        <Button size="sm" variant="ghost" onPress={onShowCurrent}>
          Show v{item.current_version_n}
        </Button>
      </div>
    );
  }
  if (item.status === 'needs_rereview') {
    const approvedN = item.latest_decision?.version_n;
    const reason =
      item.reopen_reason === null ? 'Sent back for review' : REOPEN_REASON_LABELS[item.reopen_reason];
    return (
      <div className="app-note" data-tone="alert" role="status">
        <Icon name="status.needs_rereview" />
        <span>
          <strong>Re-review: {reason}.</strong>{' '}
          {item.live_placements_count > 0
            ? `Live in ${plural(item.live_placements_count, 'placement')}.`
            : 'No live placements.'}{' '}
          {fastTrackAvailable(item)
            ? `v${String(item.current_version_n)} was generated with the new numbers.`
            : item.reopen_reason === 'approval_expired' && item.approval_expires_at !== null
              ? `Approval expired ${formatDate(item.approval_expires_at)}.`
              : ''}
        </span>
        {approvedN !== undefined && approvedN !== item.current_version_n && compareN !== approvedN && (
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              onCompareApproved(approvedN);
            }}
          >
            Compare with approved v{approvedN}
          </Button>
        )}
      </div>
    );
  }
  if (item.status === 'withdrawn') {
    return <WithdrawnNote itemId={item.id} />;
  }
  return null;
}

function WithdrawnNote({ itemId }: { itemId: number }) {
  const placements = useListPlacements(itemId);
  const pulled = (placements.data ?? []).filter((p) => p.takedown_state !== null);
  const confirmed = pulled.filter((p) => p.takedown_state === 'confirmed').length;
  const takedown =
    pulled.length === 0
      ? ''
      : confirmed === pulled.length
        ? ` Takedown confirmed for ${plural(pulled.length, 'placement')}.`
        : ` Takedown requested for ${plural(pulled.length, 'placement')}, ${String(confirmed)} confirmed.`;
  return (
    <div className="app-note" data-tone="neutral" role="status">
      <Icon name="status.withdrawn" />
      <span>
        <strong>Withdrawn.</strong>
        {takedown} The marketer can start a new round with fixed copy.
      </span>
    </div>
  );
}
