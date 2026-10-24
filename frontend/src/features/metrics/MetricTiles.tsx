/*
 * The headline numbers. Each tile is one button that opens the items behind it (the drill-down list is the
 * same computation, so its count equals the tile's). Fix-live adds the still-open clocks as a second,
 * alert-toned button: live content at risk now (spec §5.2 alert).
 */
import { Link } from '@tanstack/react-router';

import type { MetricName, MetricsSummaryOut } from '../../api/generated/model';
import { formatHours, formatRounds, sourceSplit } from './format';
import { METRIC_META } from './labels';
import type { MetricsSearch } from './search';

interface Figure {
  metric: MetricName;
  value: string;
  detail: string;
  count: number;
  split: { native_count: number; imported_count: number };
  /** Each source's own figure, when both contribute: a blended number hides the before/after. */
  bySource?: string;
}

function bySource(
  stat: { native_count: number; imported_count: number },
  native: string,
  imported: string,
): string | undefined {
  return stat.native_count > 0 && stat.imported_count > 0
    ? `Native ${native} · Imported ${imported}`
    : undefined;
}

function figures(s: MetricsSummaryOut): Figure[] {
  const duration = (metric: MetricName, stat: MetricsSummaryOut['time_to_first_review']): Figure => ({
    metric,
    value: formatHours(stat.median_hours),
    detail: stat.p90_hours === null ? 'median' : `median · p90 ${formatHours(stat.p90_hours)}`,
    count: stat.count,
    split: stat,
    bySource: bySource(stat, formatHours(stat.native_median_hours), formatHours(stat.imported_median_hours)),
  });
  return [
    duration('time_to_first_review', s.time_to_first_review),
    duration('time_per_round', s.time_per_round),
    {
      metric: 'rounds_per_item',
      value: formatRounds(s.rounds_per_item.mean),
      detail:
        s.rounds_per_item.median === null ? 'mean' : `mean · median ${String(s.rounds_per_item.median)}`,
      count: s.rounds_per_item.count,
      split: s.rounds_per_item,
      bySource: bySource(
        s.rounds_per_item,
        formatRounds(s.rounds_per_item.native_mean),
        formatRounds(s.rounds_per_item.imported_mean),
      ),
    },
    duration('time_to_fix_live', s.time_to_fix_live),
    {
      metric: 'throughput',
      value: String(s.throughput.count),
      detail: `${s.throughput.per_week.toFixed(1)} per week`,
      count: s.throughput.count,
      split: s.throughput,
    },
  ];
}

function countLine(figure: Figure): string {
  const [one, many] = METRIC_META[figure.metric].noun;
  const n = `${String(figure.count)} ${figure.count === 1 ? one : many}`;
  const split = sourceSplit(figure.split);
  return split === '' ? n : `${n} · ${split}`;
}

export function MetricTiles({
  summary,
  onDrill,
  active,
}: {
  summary: MetricsSummaryOut;
  onDrill: (metric: MetricName, open?: boolean) => void;
  active?: { metric: MetricName; open: boolean };
}) {
  return (
    <div className="app-metric-tiles" role="group" aria-label="Headline numbers">
      {figures(summary).map((figure) => {
        const meta = METRIC_META[figure.metric];
        const fixLive = figure.metric === 'time_to_fix_live';
        return (
          <div key={figure.metric} className="app-metric-tile">
            <button
              type="button"
              className="app-metric-tile-btn"
              data-active={active?.metric === figure.metric && !active.open ? 'true' : undefined}
              onClick={() => {
                onDrill(figure.metric);
              }}
            >
              <span className="app-metric-tile-label">{meta.label}</span>
              <span className="app-metric-figure">
                {figure.value}
                {figure.count > 0 && <span className="app-metric-figure-detail"> {figure.detail}</span>}
              </span>
              {figure.bySource !== undefined && (
                <span className="app-metric-tile-sources">{figure.bySource}</span>
              )}
              <span className="app-metric-tile-meta">
                {figure.count === 0 ? `No ${meta.noun[1]} in this period` : countLine(figure)}
              </span>
            </button>
            {fixLive && summary.open_fix_live.count > 0 && (
              <button
                type="button"
                className="app-metric-open"
                data-active={active?.metric === figure.metric && active.open ? 'true' : undefined}
                onClick={() => {
                  onDrill(figure.metric, true);
                }}
              >
                {`${String(summary.open_fix_live.count)} open now · oldest ${formatHours(summary.open_fix_live.oldest_hours)}`}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function WaitingRow({ summary, search }: { summary: MetricsSummaryOut; search: MetricsSearch }) {
  return (
    <div className="app-metric-waiting" role="group" aria-label="Waiting in the queue now">
      <span className="app-metric-waiting-label">Waiting in the queue now</span>
      {summary.waiting.map((w) => (
        <Link
          key={w.more_than_days}
          to="/"
          search={{
            waiting: w.more_than_days,
            ...(search.product !== undefined && { product: [search.product] }),
            ...(search.channel !== undefined && { channel: [search.channel] }),
            ...(search.partner !== undefined && { partner_id: [search.partner] }),
          }}
          className="app-metric-waiting-link"
          aria-label={`More than ${String(w.more_than_days)} days: ${String(w.count)}`}
        >
          <span className="app-metric-waiting-figure">{w.count}</span>
          <span>&gt;{w.more_than_days} days</span>
        </Link>
      ))}
      <span className="app-metric-waiting-note">Native items only; each opens its queue view.</span>
    </div>
  );
}
