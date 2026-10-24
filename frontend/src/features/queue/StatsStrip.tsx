/*
 * Counts from GET /items/stats (real numbers only, spec §2). Each figure that has a matching view opens it.
 * "In queue" has no view of its own (it excludes changes requested, which All active includes), so it is a
 * plain figure. Re-review counts status = needs re-review; the view also keeps re-reviews already opened.
 */
import { useGetQueueStats } from '../../api/generated/items/items';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import type { BuiltInViewId } from './search';

const FIGURES: readonly {
  key: 'mine' | 'unassigned' | 'waiting_over_3_days' | 'needs_rereview';
  label: string;
  view: BuiltInViewId;
  alert?: boolean;
}[] = [
  { key: 'mine', label: 'My queue', view: 'mine' },
  { key: 'unassigned', label: 'Unassigned', view: 'unassigned' },
  { key: 'waiting_over_3_days', label: 'Waiting >3 days', view: 'waiting' },
  { key: 'needs_rereview', label: 'Needs re-review', view: 'rereview', alert: true },
];

export function StatsStrip({
  onPick,
  active,
}: {
  onPick: (view: BuiltInViewId) => void;
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
      <div className="app-stat">
        {data === undefined ? (
          <span className="app-skeleton h-6 w-8" />
        ) : (
          <span className="app-stat-figure">{data.open}</span>
        )}{' '}
        <span className="app-stat-label">In queue</span>
      </div>
      {FIGURES.map((figure) => (
        <button
          key={figure.key}
          type="button"
          className="app-stat app-stat-btn"
          data-active={active === figure.view ? 'true' : undefined}
          data-alert={
            figure.alert === true && data !== undefined && data[figure.key] > 0 ? 'true' : undefined
          }
          disabled={data === undefined}
          onClick={() => {
            onPick(figure.view);
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
