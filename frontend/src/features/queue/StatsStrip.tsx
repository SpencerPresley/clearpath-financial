/*
 * Counts from GET /items/stats (real numbers only, spec §2). Every figure opens the view it is the total of,
 * with the filters the server counted it with (`stats.filters`), so the list it opens holds exactly that many
 * items (ledger ruling: a number that doesn't match its list loses the team's trust).
 */
import { useGetQueueStats } from '../../api/generated/items/items';
import type { QueueStatFiltersOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { STAT_VIEWS, statSearch } from './search';
import type { BuiltInViewId, QueueSearch } from './search';

const FIGURES: readonly { key: keyof QueueStatFiltersOut; label: string; alert?: boolean }[] = [
  { key: 'open', label: 'In queue' },
  { key: 'mine', label: 'My queue' },
  { key: 'unassigned', label: 'Unassigned' },
  { key: 'waiting_over_3_days', label: 'Waiting >3 days' },
  { key: 'needs_rereview', label: 'Needs re-review', alert: true },
];

export function StatsStrip({
  onPick,
  active,
}: {
  onPick: (search: QueueSearch) => void;
  active?: BuiltInViewId;
}) {
  const stats = useGetQueueStats();

  if (stats.isError) {
    return (
      <div className="app-stats" role="status">
        <span className="app-inline-error">
          <Icon name="feedback.error" size={14} />
          <span>Couldn't load queue counts.</span>
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              void stats.refetch();
            }}
          >
            Retry
          </Button>
        </span>
      </div>
    );
  }

  const data = stats.data;
  return (
    <div className="app-stats" aria-label="Queue counts" role="group" aria-busy={data === undefined}>
      {FIGURES.map((figure) => (
        <button
          key={figure.key}
          type="button"
          className="app-stat app-stat-btn"
          data-active={active === STAT_VIEWS[figure.key] ? 'true' : undefined}
          data-alert={
            figure.alert === true && data !== undefined && data[figure.key] > 0 ? 'true' : undefined
          }
          disabled={data === undefined}
          onClick={() => {
            if (data !== undefined) onPick(statSearch(figure.key, data.filters[figure.key]));
          }}
        >
          {data === undefined ? (
            <span className="app-skeleton h-6 w-8" />
          ) : (
            <span className="app-stat-figure">{data[figure.key]}</span>
          )}{' '}
          <span className="app-stat-label">{figure.label}</span>
        </button>
      ))}
    </div>
  );
}
