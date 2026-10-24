/*
 * The headline numbers. Each tile is one button that opens the items behind it (the drill-down list is the
 * same computation, so its count equals the tile's). Every tile has the same four lines: label, figure, how the
 * figure is computed, and how many measurements it rests on, split by source.
 *
 * When native and imported data both contribute to a duration or a mean, the tile shows each source's figure
 * side by side instead of one blended number: the two are measured differently (event log to the hour; tracker
 * comments to the day), so a blend moves with the native/imported mix rather than with the team's speed.
 * Throughput is a count, so native + imported is a true total.
 */
import { Link } from '@tanstack/react-router';

import type { MetricName, MetricsSummaryOut } from '../../api/generated/model';
import { Icon } from '../../ui/Icon';
import { formatHours, formatRounds } from './format';
import { METRIC_META } from './labels';
import type { MetricsSearch } from './search';

/** p90 of fewer measurements than this is just the maximum; it isn't shown. */
const P90_MIN = 5;

export const DRILL_ID = 'metric-drill';

interface Split {
  native_count: number;
  imported_count: number;
}

interface Figure {
  metric: MetricName;
  /** One figure, or one per source when both contribute. */
  values: { value: string; source?: 'native' | 'imported' }[];
  detail: string;
  count: number;
  split: Split;
}

function both(split: Split): boolean {
  return split.native_count > 0 && split.imported_count > 0;
}

function figures(s: MetricsSummaryOut): Figure[] {
  const duration = (metric: MetricName, stat: MetricsSummaryOut['time_to_first_review']): Figure => ({
    metric,
    values: both(stat)
      ? [
          { value: formatHours(stat.native_median_hours), source: 'native' },
          { value: formatHours(stat.imported_median_hours), source: 'imported' },
        ]
      : [{ value: formatHours(stat.median_hours) }],
    detail:
      !both(stat) && stat.p90_hours !== null && stat.count >= P90_MIN
        ? `median · p90 ${formatHours(stat.p90_hours)}`
        : 'median',
    count: stat.count,
    split: stat,
  });
  const rounds = s.rounds_per_item;
  return [
    duration('time_to_first_review', s.time_to_first_review),
    duration('time_per_round', s.time_per_round),
    {
      metric: 'rounds_per_item',
      values: both(rounds)
        ? [
            { value: formatRounds(rounds.native_mean), source: 'native' },
            { value: formatRounds(rounds.imported_mean), source: 'imported' },
          ]
        : [{ value: formatRounds(rounds.mean) }],
      detail: both(rounds) || rounds.median === null ? 'mean' : `mean · median ${String(rounds.median)}`,
      count: rounds.count,
      split: rounds,
    },
    duration('time_to_fix_live', s.time_to_fix_live),
    {
      metric: 'throughput',
      values: [{ value: String(s.throughput.count) }],
      detail: `${s.throughput.per_week.toFixed(1)} per week`,
      count: s.throughput.count,
      split: s.throughput,
    },
  ];
}

/** "98 items", "40 native", "58 imported" as separate unbreakable segments. */
function countSegments(figure: Figure): string[] {
  const meta = METRIC_META[figure.metric];
  if (figure.count === 0) return [`No ${meta.noun[1]} in this period`];
  const [one, many] = meta.noun;
  const n = `${String(figure.count)} ${figure.count === 1 ? one : many}`;
  const { native_count: native, imported_count: imported } = figure.split;
  if (native > 0 && imported > 0) return [n, `${String(native)} native`, `${String(imported)} imported`];
  return [n, native > 0 ? 'native only' : 'imported only'];
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
  const open = summary.open_fix_live;
  return (
    <div className="app-metric-tiles" role="group" aria-label="Headline numbers">
      {figures(summary).map((figure) => {
        const meta = METRIC_META[figure.metric];
        const expanded = active?.metric === figure.metric && !active.open;
        return (
          <div key={figure.metric} className="app-metric-tile">
            <button
              type="button"
              className="app-metric-tile-btn"
              data-drill-trigger={figure.metric}
              data-active={expanded ? 'true' : undefined}
              aria-expanded={expanded}
              aria-controls={expanded ? DRILL_ID : undefined}
              onClick={() => {
                onDrill(figure.metric);
              }}
            >
              <span className="app-metric-tile-label">{meta.label}</span>
              <span className="app-metric-figures">
                {figure.values.map(({ value, source }) => (
                  <span key={source ?? 'all'} className="app-metric-figure">
                    {value}
                    {source !== undefined && <span className="app-metric-figure-source"> {source}</span>}
                  </span>
                ))}
              </span>
              <span className="app-metric-tile-detail">{figure.count > 0 ? figure.detail : '\u00a0'}</span>
              <span className="app-metric-tile-meta">
                {countSegments(figure).map((segment, i) => (
                  <span key={segment} className="app-metric-segment">
                    {i > 0 && '· '}
                    {segment}
                  </span>
                ))}
              </span>
            </button>
            {figure.metric === 'time_to_fix_live' && open.count > 0 && (
              <button
                type="button"
                className="app-metric-open"
                data-drill-trigger={`${figure.metric}:open`}
                data-active={active?.metric === figure.metric && active.open ? 'true' : undefined}
                aria-expanded={active?.metric === figure.metric && active.open}
                onClick={() => {
                  onDrill(figure.metric, true);
                }}
              >
                <Icon name="status.needs_rereview" size={13} className="shrink-0" />
                {`${String(open.count)} ${open.count === 1 ? 're-review' : 're-reviews'} open · oldest ${formatHours(open.oldest_hours)}`}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function TileSkeleton() {
  return (
    <div className="app-metric-tiles" role="status" aria-label="Loading the numbers">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="app-metric-tile">
          <div className="app-metric-tile-btn">
            <span className="app-skeleton h-4 w-28" />
            <span className="app-skeleton h-7 w-20" />
            <span className="app-skeleton h-4 w-24" />
            <span className="app-skeleton h-4 w-36" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function WaitingRow({ summary, search }: { summary?: MetricsSummaryOut; search: MetricsSearch }) {
  return (
    <div className="app-metric-waiting" role="group" aria-label="Waiting in the queue now">
      <span className="app-metric-waiting-label">Waiting in the queue now</span>
      {summary === undefined
        ? [3, 7, 14, 30].map((days) => <span key={days} className="app-skeleton h-5 w-16" />)
        : summary.waiting.map((w) => (
            <Link
              key={w.more_than_days}
              to="/queue"
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
