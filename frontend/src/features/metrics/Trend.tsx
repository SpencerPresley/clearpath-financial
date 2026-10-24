/*
 * One metric over time, per week or month, as bars (TanStack Charts, SVG) or as the same numbers in a table.
 * Throughput stacks native and imported decisions so the imported share is visible; durations show the
 * bucket's median, and a bucket with no measurements is a gap, not a zero. Clicking a bar, or a table row's
 * button, opens that bucket's items.
 */
import { barY, defineChart } from '@tanstack/charts';
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

interface Bar {
  label: string;
  point: MetricPointOut;
  source: 'Native' | 'Imported';
  value: number;
}

function formatValue(metric: MetricName, value: number | null): string {
  const unit = METRIC_META[metric].unit;
  if (unit === 'hours') return formatHours(value);
  if (unit === 'rounds') return formatRounds(value);
  return value === null ? '—' : String(value);
}

function bars(metric: MetricName, points: readonly MetricPointOut[], bucket: MetricBucket): Bar[] {
  const out: Bar[] = [];
  for (const point of points) {
    const label = bucketLabel(point.period_start, bucket);
    if (metric === 'throughput') {
      out.push({ label, point, source: 'Native', value: point.native_count });
      out.push({ label, point, source: 'Imported', value: point.imported_count });
    } else if (point.value !== null) {
      out.push({ label, point, source: 'Native', value: point.value });
    }
  }
  return out;
}

function chartName(metric: MetricName, bucket: MetricBucket): string {
  const per = bucket === 'week' ? 'week' : 'month';
  const base = `${METRIC_META[metric].label} by ${per}`;
  if (metric === 'throughput') return `${base}, native and imported`;
  return METRIC_META[metric].unit === 'hours' ? `${base}, median` : `${base}, mean`;
}

function TrendChart({
  metric,
  bucket,
  points,
  onPick,
}: {
  metric: MetricName;
  bucket: MetricBucket;
  points: readonly MetricPointOut[];
  onPick: (point: MetricPointOut) => void;
}) {
  const definition = useMemo(() => {
    const labels = points.map((p) => bucketLabel(p.period_start, bucket));
    return defineChart({
      marks: [
        barY(bars(metric, points, bucket), {
          x: 'label',
          y: 'value',
          z: 'source',
          key: (bar) => `${bar.label}-${bar.source}`,
        }),
      ],
      scales: {
        x: { scale: scaleBand().domain(labels).padding(0.3) },
        y: {
          scale: scaleLinear,
          nice: true,
          grid: true,
          axis: { ticks: { format: (value) => formatValue(metric, value) } },
        },
      },
      tooltip,
    });
  }, [metric, bucket, points]);

  return (
    <Chart
      definition={definition}
      height={HEIGHT}
      ariaLabel={chartName(metric, bucket)}
      ariaDescription="Each bar opens the items behind it. The same numbers are in the table view."
      className="app-metric-chart"
      onSelect={(point) => {
        if (point !== null) onPick(point.datum.point);
      }}
    />
  );
}

function TrendTable({
  metric,
  bucket,
  points,
  onPick,
}: {
  metric: MetricName;
  bucket: MetricBucket;
  points: readonly MetricPointOut[];
  onPick: (point: MetricPointOut) => void;
}) {
  const meta = METRIC_META[metric];
  return (
    <table className="app-metric-table" aria-label={chartName(metric, bucket)}>
      <thead>
        <tr>
          <th scope="col">{bucket === 'week' ? 'Week of' : 'Month'}</th>
          {meta.unit !== 'decisions' && (
            <th scope="col" className="app-num">
              {meta.unit === 'hours' ? 'Median' : 'Mean'}
            </th>
          )}
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
              {meta.unit !== 'decisions' && <td className="app-num">{formatValue(metric, point.value)}</td>}
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
  const points = series.data?.points ?? [];
  const empty = series.data !== undefined && points.every((p) => p.count === 0);

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
    body = <TrendTable metric={metric} bucket={bucket} points={points} onPick={onPick} />;
  } else {
    body = <TrendChart metric={metric} bucket={bucket} points={points} onPick={onPick} />;
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
        {metric === 'throughput' && view === 'chart' && (
          <span className="app-metric-legend" aria-hidden="true">
            <span className="app-metric-swatch" data-series="native" /> Native
            <span className="app-metric-swatch" data-series="imported" /> Imported
          </span>
        )}
      </p>
      {body}
    </section>
  );
}
