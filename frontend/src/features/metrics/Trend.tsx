/*
 * One metric over time, per week or month, as bars (TanStack Charts, SVG) or as the same numbers in a table.
 * Throughput stacks native and imported decisions so the imported share is visible; durations show the
 * bucket's median, and a bucket with no measurements is a gap, not a zero. Clicking a bar, or a table row's
 * button, opens that bucket's items.
 */
import { barY, defineChart, group } from '@tanstack/charts';
import { Chart } from '@tanstack/charts/react';
import { scaleBand } from '@tanstack/charts/scales/band';
import { scaleLinear } from '@tanstack/charts/scales/linear';
import { tooltip } from '@tanstack/charts/tooltip';
import { useMemo } from 'react';
import { ToggleButton, ToggleButtonGroup } from 'react-aria-components';

import { useGetMetricSeries } from '../../api/generated/metrics/metrics';
import type {
  GetMetricsSummaryParams,
  MetricBucket,
  MetricName,
  MetricPointOut,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import { bucketLabel, formatHours, formatRounds, rangeLabel, sourceSplit } from './format';
import { METRIC_META, METRIC_ORDER } from './labels';

const HEIGHT = 240;

function formatValue(metric: MetricName, value: number | null): string {
  const unit = METRIC_META[metric].unit;
  if (unit === 'hours') return formatHours(value);
  if (unit === 'rounds') return formatRounds(value);
  return value === null ? '—' : String(value);
}

export type Source = 'Native' | 'Imported';

export interface Bar {
  label: string;
  point: MetricPointOut;
  source: Source;
  /** In the chart's unit: hours or days for durations (see `chartRows`), else as served. */
  value: number;
}

export interface ChartRows {
  bars: Bar[];
  /** Sources with at least one value, in fixed order: the legend and the group slots. */
  sources: Source[];
  /** Durations over two days chart in days, so ticks read 2 d, 4 d, not 8.3 d. */
  unit: 'h' | 'd' | null;
}

/**
 * One bar per source per bucket. Throughput stacks (native + imported = decisions); durations and rounds
 * group side by side, since a median of the two sources together would hide the before/after.
 */
export function chartRows(
  metric: MetricName,
  points: readonly MetricPointOut[],
  bucket: MetricBucket,
): ChartRows {
  const raw: Bar[] = [];
  for (const point of points) {
    const label = bucketLabel(point.period_start, bucket);
    const values: [Source, number | null][] =
      metric === 'throughput'
        ? [
            ['Native', point.native_count],
            ['Imported', point.imported_count],
          ]
        : [
            ['Native', point.native_value],
            ['Imported', point.imported_value],
          ];
    for (const [source, value] of values) {
      if (value !== null) raw.push({ label, point, source, value });
    }
  }
  const present = (source: Source) =>
    raw.some((b) => b.source === source && (metric !== 'throughput' || b.value > 0));
  const sources = (['Native', 'Imported'] as const).filter(present);
  if (METRIC_META[metric].unit !== 'hours') return { bars: raw, sources, unit: null };
  const days = raw.some((b) => b.value >= 48);
  return {
    bars: days ? raw.map((b) => ({ ...b, value: b.value / 24 })) : raw,
    sources,
    unit: days ? 'd' : 'h',
  };
}

const FILL: Record<Source, string> = {
  Native: 'var(--color-chart-native)',
  Imported: 'var(--color-chart-imported)',
};

export function chartName(metric: MetricName, bucket: MetricBucket, sources: readonly Source[]): string {
  const per = bucket === 'week' ? 'week' : 'month';
  const unit = METRIC_META[metric].unit;
  const stat = unit === 'hours' ? ', median' : unit === 'rounds' ? ', mean' : '';
  const only = sources[0];
  const split =
    sources.length === 2 ? ', native and imported' : only === undefined ? '' : `, ${only.toLowerCase()} only`;
  return `${METRIC_META[metric].label} by ${per}${stat}${split}`;
}

interface ViewProps {
  metric: MetricName;
  bucket: MetricBucket;
  points: readonly MetricPointOut[];
  rows: ChartRows;
  onPick: (point: MetricPointOut) => void;
}

function TrendChart({ metric, bucket, points, rows, onPick }: ViewProps) {
  const definition = useMemo(() => {
    const labels = points.map((p) => bucketLabel(p.period_start, bucket));
    const tick = (value: number) =>
      rows.unit === null ? formatValue(metric, value) : `${String(Math.round(value * 10) / 10)} ${rows.unit}`;
    return defineChart({
      marks: [
        barY(rows.bars, {
          x: 'label',
          y: 'value',
          z: 'source',
          fill: (bar) => FILL[bar.source],
          key: (bar) => `${bar.label}-${bar.source}`,
          ...(metric !== 'throughput' && {
            layout: group({ scale: scaleBand().domain(rows.sources).padding(0.1) }),
          }),
        }),
      ],
      scales: {
        x: { scale: scaleBand().domain(labels).padding(0.3) },
        y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: tick } } },
      },
      tooltip,
    });
  }, [metric, bucket, points, rows]);

  return (
    <Chart
      definition={definition}
      height={HEIGHT}
      ariaLabel={chartName(metric, bucket, rows.sources)}
      ariaDescription="Each bar opens the items behind it. The same numbers are in the table view."
      className="app-metric-chart"
      onSelect={(point) => {
        if (point !== null) onPick(point.datum.point);
      }}
    />
  );
}

function TrendTable({ metric, bucket, points, rows, onPick }: ViewProps) {
  const meta = METRIC_META[metric];
  const stat = meta.unit === 'hours' ? 'median' : 'mean';
  // Durations and rounds: one value column per source present, as the chart groups them.
  const valueColumns = meta.unit === 'decisions' ? [] : rows.sources;
  return (
    <table className="app-metric-table" aria-label={chartName(metric, bucket, rows.sources)}>
      <thead>
        <tr>
          <th scope="col">{bucket === 'week' ? 'Week of' : 'Month'}</th>
          {valueColumns.map((source) => (
            <th key={source} scope="col" className="app-num">
              {source} {stat}
            </th>
          ))}
          <th scope="col" className="app-num">
            {meta.noun[1].replace(/^./, (c) => c.toUpperCase())}
          </th>
          <th scope="col">Source</th>
          <th scope="col">
            <span className="sr-only">Items</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {points.map((point) => {
          const label = bucketLabel(point.period_start, bucket);
          const range = rangeLabel(point.from_date, point.to_date);
          return (
            <tr key={point.period_start}>
              <th scope="row">{label}</th>
              {valueColumns.map((source) => (
                <td key={source} className="app-num">
                  {formatValue(metric, source === 'Native' ? point.native_value : point.imported_value)}
                </td>
              ))}
              <td className="app-num">{point.count}</td>
              <td className="app-muted">{sourceSplit(point)}</td>
              <td className="app-num">
                {point.count > 0 && (
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Items for ${range}`}
                    onPress={() => {
                      onPick(point);
                    }}
                  >
                    Items
                  </Button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function Trend({
  params,
  metric,
  bucket,
  view,
  onChange,
  onPick,
}: {
  params: GetMetricsSummaryParams;
  metric: MetricName;
  bucket: MetricBucket;
  view: 'chart' | 'table';
  onChange: (change: { chart?: MetricName; bucket?: MetricBucket; view?: 'chart' | 'table' }) => void;
  onPick: (point: MetricPointOut) => void;
}) {
  const series = useGetMetricSeries({ ...params, metric, bucket });
  const served = series.data?.points;
  const points = useMemo(() => served ?? [], [served]);
  const empty = series.data !== undefined && points.every((p) => p.count === 0);
  const rows = useMemo(() => chartRows(metric, points, bucket), [metric, points, bucket]);

  let body: React.ReactNode;
  if (series.isPending) {
    body = (
      <div className="app-metric-chart-skeleton app-skeleton" role="status" aria-label="Loading the trend" />
    );
  } else if (series.isError) {
    body = (
      <div className="app-metric-chart-error" role="alert">
        <Icon name="feedback.error" size={14} className="app-metric-error-icon" />
        <span>Couldn&apos;t load the trend. {apiErrorMessage(series.error)}</span>
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void series.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else if (empty) {
    body = <p className="app-metric-chart-empty">No {METRIC_META[metric].noun[1]} in this period.</p>;
  } else if (view === 'table') {
    body = <TrendTable metric={metric} bucket={bucket} points={points} rows={rows} onPick={onPick} />;
  } else {
    body = <TrendChart metric={metric} bucket={bucket} points={points} rows={rows} onPick={onPick} />;
  }

  return (
    <section className="app-metric-trend" aria-label="Trend">
      <div className="app-metric-trend-bar">
        <ToggleButtonGroup
          aria-label="Metric"
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={[metric]}
          onSelectionChange={(keys) => {
            const next = [...keys][0];
            if (next !== undefined) onChange({ chart: String(next) as MetricName });
          }}
          className="app-segmented"
        >
          {METRIC_ORDER.map((m) => (
            <ToggleButton key={m} id={m} className="app-segment">
              {METRIC_META[m].label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <div className="app-metric-trend-controls">
          <ToggleButtonGroup
            aria-label="Bucket"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[bucket]}
            onSelectionChange={(keys) => {
              const next = [...keys][0];
              if (next !== undefined) onChange({ bucket: String(next) as MetricBucket });
            }}
            className="app-segmented"
          >
            <ToggleButton id="week" className="app-segment">
              Weekly
            </ToggleButton>
            <ToggleButton id="month" className="app-segment">
              Monthly
            </ToggleButton>
          </ToggleButtonGroup>
          <ToggleButtonGroup
            aria-label="Show as"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[view]}
            onSelectionChange={(keys) => {
              const next = [...keys][0];
              if (next !== undefined) onChange({ view: next === 'table' ? 'table' : 'chart' });
            }}
            className="app-segmented"
          >
            <ToggleButton id="chart" className="app-segment">
              Chart
            </ToggleButton>
            <ToggleButton id="table" className="app-segment">
              Table
            </ToggleButton>
          </ToggleButtonGroup>
        </div>
      </div>
      <p className="app-metric-trend-caption">
        {METRIC_META[metric].definition}
        {METRIC_META[metric].importedNote !== undefined && ` ${METRIC_META[metric].importedNote}`}
        {view === 'chart' && !empty && rows.sources.length > 0 && (
          <span className="app-metric-legend" aria-hidden="true">
            {rows.sources.map((source) => (
              <span key={source} className="app-metric-legend-item">
                <span className="app-metric-swatch" data-series={source.toLowerCase()} /> {source}
              </span>
            ))}
          </span>
        )}
      </p>
      {body}
    </section>
  );
}
