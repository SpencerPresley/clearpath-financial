/*
 * Metrics (product-spec "Metrics"): real numbers computed from the event log plus the imported tracker's own
 * dates, never placeholders. Every number says how much of it is native and how much imported, and opens the
 * items behind it. The period, filters, trend, and open drill-down are all in the URL.
 */
import { useNavigate, useSearch } from '@tanstack/react-router';
import { ToggleButton, ToggleButtonGroup } from 'react-aria-components';

import { useGetMetricsSummary } from '../../api/generated/metrics/metrics';
import { Channel, Product } from '../../api/generated/model';
import type { MetricName, MetricPointOut } from '../../api/generated/model';
import { useListPartners } from '../../api/generated/partners/partners';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { CheckboxField, SelectField, TextInput } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { CHANNEL_LABELS, formatDate, PRODUCT_LABELS } from '../../ui/labels';
import { DrillDown } from './DrillDown';
import { periodFor } from './format';
import { MetricTiles, WaitingRow } from './MetricTiles';
import { metricsParams } from './search';
import type { MetricsSearch, Range } from './search';
import { Trend } from './Trend';

const RANGE_LABELS: Record<Range, string> = {
  '4w': '4 weeks',
  '13w': '13 weeks',
  '12m': '12 months',
  custom: 'Custom',
};

const ALL = 'all';

function TileSkeleton() {
  return (
    <div className="app-metric-tiles" role="status" aria-label="Loading the numbers">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="app-metric-tile">
          <div className="app-metric-tile-btn">
            <span className="app-skeleton h-4 w-28" />
            <span className="app-skeleton h-7 w-20" />
            <span className="app-skeleton h-4 w-36" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function MetricsPage() {
  const search = useSearch({ from: '/metrics' });
  const navigate = useNavigate({ from: '/metrics' });
  const period = periodFor(search);
  const params = metricsParams(search, period);
  const summary = useGetMetricsSummary(params);
  const partners = useListPartners();

  function update(change: Partial<MetricsSearch>, { keepDrill = false } = {}) {
    const reset = keepDrill ? {} : { drill: undefined, dfrom: undefined, dto: undefined, open: undefined };
    void navigate({ search: (prev) => ({ ...prev, ...reset, ...change }), replace: false });
  }

  function drill(metric: MetricName, open = false) {
    update({ drill: metric, dfrom: undefined, dto: undefined, open: open || undefined });
  }

  function drillPoint(point: MetricPointOut) {
    update({ drill: search.chart, dfrom: point.from_date, dto: point.to_date, open: undefined });
  }

  const data = summary.data;
  const empty =
    data?.throughput.count === 0 && data.time_to_first_review.count === 0 && data.open_fix_live.count === 0;
  const showImported = search.legacy !== false && data?.imported_from != null && data.imported_to != null;

  let headline: React.ReactNode;
  if (summary.isPending) {
    headline = <TileSkeleton />;
  } else if (summary.isError) {
    headline = (
      <div className="app-metric-error" role="alert">
        <Icon name="feedback.error" size={14} className="app-metric-error-icon" />
        <span>{apiErrorMessage(summary.error)}</span>
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void summary.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else if (empty) {
    headline = (
      <EmptyState
        icon="nav.metrics"
        title="No decisions in this period"
        action={
          search.range !== '12m' && (
            <Button
              size="sm"
              onPress={() => {
                update({ range: '12m', from: undefined, to: undefined });
              }}
            >
              Last 12 months
            </Button>
          )
        }
      >
        {formatDate(data.period_from)} – {formatDate(data.period_to)} has no reviews completed
        {search.legacy === false ? ' (imported history excluded)' : ''}.
      </EmptyState>
    );
  } else {
    headline = (
      <MetricTiles
        summary={summary.data}
        onDrill={drill}
        active={search.drill === undefined ? undefined : { metric: search.drill, open: search.open === true }}
      />
    );
  }

  const partnerOptions = [
    { id: ALL, label: 'All partners' },
    ...(partners.data ?? []).map((p) => ({ id: String(p.id), label: p.name })),
  ];

  return (
    <div className="app-metrics">
      <header className="app-metrics-header">
        <h1 className="app-page-title">Metrics</h1>
        <div className="app-metrics-filters" role="group" aria-label="Filters">
          <ToggleButtonGroup
            aria-label="Period"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[search.range]}
            onSelectionChange={(keys) => {
              const next = [...keys][0] as Range | undefined;
              if (next === undefined) return;
              update(
                next === 'custom'
                  ? { range: next, from: period.from, to: period.to }
                  : { range: next, from: undefined, to: undefined },
              );
            }}
            className="app-segmented"
          >
            {(Object.keys(RANGE_LABELS) as Range[]).map((range) => (
              <ToggleButton key={range} id={range} className="app-segment">
                {RANGE_LABELS[range]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          {search.range === 'custom' && (
            <>
              <TextInput
                type="date"
                label="From"
                value={period.from}
                onChange={(value) => {
                  if (value !== '') update({ from: value });
                }}
                className="app-metrics-date"
              />
              <TextInput
                type="date"
                label="To"
                value={period.to}
                onChange={(value) => {
                  if (value !== '') update({ to: value });
                }}
                className="app-metrics-date"
              />
            </>
          )}
          <SelectField
            label="Product"
            hideLabel
            size="sm"
            value={search.product ?? ALL}
            onChange={(value) => {
              update({ product: value === null || value === ALL ? undefined : value });
            }}
            options={[
              { id: ALL, label: 'All products' },
              ...Object.values(Product).map((p) => ({ id: p, label: PRODUCT_LABELS[p] })),
            ]}
          />
          <SelectField
            label="Channel"
            hideLabel
            size="sm"
            value={search.channel ?? ALL}
            onChange={(value) => {
              update({ channel: value === null || value === ALL ? undefined : value });
            }}
            options={[
              { id: ALL, label: 'All channels' },
              ...Object.values(Channel).map((c) => ({ id: c, label: CHANNEL_LABELS[c] })),
            ]}
          />
          <SelectField
            label="Partner"
            hideLabel
            size="sm"
            isDisabled={partners.isError}
            value={search.partner === undefined ? ALL : String(search.partner)}
            onChange={(value) => {
              update({ partner: value === null || value === ALL ? undefined : Number(value) });
            }}
            options={partnerOptions}
          />
          <CheckboxField
            isSelected={search.legacy !== false}
            onChange={(selected) => {
              update({ legacy: selected ? undefined : false });
            }}
          >
            Include imported history
          </CheckboxField>
        </div>
      </header>

      {showImported && (
        <p className="app-metrics-provenance">
          <Icon name="feedback.info" size={14} />
          <span>
            Imported tracker history covers {formatDate(data.imported_from ?? '')} –{' '}
            {formatDate(data.imported_to ?? '')}, at day precision. Native numbers come from the event log.
          </span>
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              update({
                range: 'custom',
                from: data.imported_from ?? undefined,
                to: data.imported_to ?? undefined,
              });
            }}
          >
            Show that period
          </Button>
        </p>
      )}
      {partners.isError && (
        <p className="app-metrics-provenance app-muted">
          Partners couldn&apos;t load; the partner filter is off.
        </p>
      )}

      {headline}
      {data !== undefined && <WaitingRow summary={data} search={search} />}

      {search.drill !== undefined && (
        <DrillDown
          params={params}
          metric={search.drill}
          range={{ from: search.dfrom ?? period.from, to: search.dto ?? period.to }}
          openOnly={search.open === true}
          onClose={() => {
            update({});
          }}
        />
      )}

      <Trend
        params={params}
        metric={search.chart}
        bucket={search.bucket}
        view={search.view}
        onChange={(change) => {
          update(change, { keepDrill: true });
        }}
        onPick={drillPoint}
      />
    </div>
  );
}
