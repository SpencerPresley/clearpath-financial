/*
 * Metrics (product-spec "Metrics"): real numbers computed from the event log plus the imported tracker's own
 * dates, never placeholders. Every number says how much of it is native and how much imported, and opens the
 * items behind it. The period, filters, trend, and open drill-down are all in the URL.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
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
import { MetricTiles, TileSkeleton, WaitingRow } from './MetricTiles';
import { isServerError } from './retry';
import { hasFilters, metricsParams } from './search';
import type { MetricsSearch, Range } from './search';
import { Trend } from './Trend';

const RANGE_LABELS: Record<Range, string> = {
  '4w': '4 weeks',
  '13w': '13 weeks',
  '12m': '12 months',
  custom: 'Custom',
};

const ALL = 'all';
const DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Custom dates are a draft until applied (Enter, Apply, or leaving the field): the browser's date input
 * re-renders mid-typing if every keystroke round-trips through the URL, and a half-typed date is a different
 * period. A backwards range is refused here instead of asking the server.
 */
function CustomRange({
  from,
  to,
  onApply,
}: {
  from: string;
  to: string;
  onApply: (range: { from: string; to: string }) => void;
}) {
  const [draft, setDraft] = useState({ from, to });
  const complete = DATE.test(draft.from) && DATE.test(draft.to);
  const backwards = complete && draft.from > draft.to;
  const changed = draft.from !== from || draft.to !== to;

  function apply() {
    if (complete && !backwards && changed) onApply(draft);
  }

  return (
    <form
      className="app-metrics-range"
      aria-label="Custom period"
      onSubmit={(event) => {
        event.preventDefault();
        apply();
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) apply();
      }}
    >
      <TextInput
        type="date"
        label="From"
        value={draft.from}
        onChange={(value) => {
          setDraft((d) => ({ ...d, from: value }));
        }}
        className="app-metrics-date"
      />
      <TextInput
        type="date"
        label="To"
        value={draft.to}
        onChange={(value) => {
          setDraft((d) => ({ ...d, to: value }));
        }}
        errorMessage={backwards ? 'Ends before it starts.' : null}
        className="app-metrics-date"
      />
      <Button type="submit" size="sm" isDisabled={!complete || backwards || !changed}>
        Apply
      </Button>
    </form>
  );
}

function focusTrigger(selector: string) {
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(`[data-drill-trigger="${selector}"]`)?.focus();
  });
}

export function MetricsPage() {
  const search = useSearch({ from: '/metrics' });
  const navigate = useNavigate({ from: '/metrics' });
  const queryClient = useQueryClient();
  const period = periodFor(search);
  const params = metricsParams(search, period);
  // A hand-edited URL can carry a backwards period; never send it (the server would refuse it).
  const ordered = period.from <= period.to;
  const summary = useGetMetricsSummary(params, { query: { enabled: ordered } });
  const partners = useListPartners();
  const importedIncluded = search.imported !== false;

  function update(change: Partial<MetricsSearch>, { keepDrill = false, replace = false } = {}) {
    const reset = keepDrill ? {} : { drill: undefined, dfrom: undefined, dto: undefined, open: undefined };
    return navigate({ search: (prev) => ({ ...prev, ...reset, ...change }), replace });
  }

  function drill(metric: MetricName, open = false) {
    void update({ drill: metric, dfrom: undefined, dto: undefined, open: open || undefined });
  }

  function drillPoint(point: MetricPointOut) {
    void update({ drill: search.chart, dfrom: point.from_date, dto: point.to_date, open: undefined });
  }

  function closeDrill() {
    const trigger = search.open === true ? `${search.drill ?? ''}:open` : (search.drill ?? '');
    void update({}).then(() => {
      focusTrigger(trigger);
    });
  }

  function retryAll() {
    void queryClient.refetchQueries({
      predicate: (q) => typeof q.queryKey[0] === 'string' && q.queryKey[0].startsWith('/api/metrics'),
    });
  }

  function clearFilters() {
    void update({ product: undefined, channel: undefined, partner: undefined, imported: undefined });
  }

  const data = summary.data;
  const empty =
    data?.throughput.count === 0 && data.time_to_first_review.count === 0 && data.open_fix_live.count === 0;

  let headline: React.ReactNode;
  if (!ordered) {
    headline = (
      <div className="app-metric-error" role="alert">
        <Icon name="feedback.error" size={14} className="app-metric-error-icon" />
        <span>
          The period ends before it starts ({formatDate(period.from)} – {formatDate(period.to)}). Pick the
          dates in order.
        </span>
      </div>
    );
  } else if (summary.isPending) {
    headline = <TileSkeleton />;
  } else if (summary.isError) {
    headline = (
      <div className="app-metric-error" role="alert">
        <Icon name="feedback.error" size={14} className="app-metric-error-icon" />
        <span>Couldn&apos;t load the headline numbers. {apiErrorMessage(summary.error)}</span>
        {isServerError(summary.error) && (
          <Button size="sm" variant="ghost" onPress={retryAll}>
            Retry
          </Button>
        )}
      </div>
    );
  } else if (empty) {
    const filtered = hasFilters(search);
    headline = (
      <EmptyState
        icon="nav.metrics"
        title="No decisions in this period"
        action={
          filtered ? (
            <Button size="sm" onPress={clearFilters}>
              Clear filters
            </Button>
          ) : search.range !== '12m' ? (
            <Button
              size="sm"
              onPress={() => {
                void update({ range: '12m', from: undefined, to: undefined });
              }}
            >
              Last 12 months
            </Button>
          ) : undefined
        }
      >
        {formatDate(data.period_from)} – {formatDate(data.period_to)} has no decisions
        {filtered ? ' for these filters' : ''}.
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

  let provenance: React.ReactNode = null;
  if (partners.isError) {
    provenance = <span>Partners couldn&apos;t load; the partner filter is off.</span>;
  } else if (importedIncluded && data?.imported_from != null && data.imported_to != null) {
    const { imported_from: from, imported_to: to } = data;
    provenance = (
      <>
        <Icon name="feedback.info" size={14} />
        <span>
          Imported tracker history covers {formatDate(from)} – {formatDate(to)}, at day precision. Native
          numbers come from the event log.
        </span>
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void update({ range: 'custom', from, to });
          }}
        >
          Show that period
        </Button>
      </>
    );
  } else if (!importedIncluded) {
    provenance = <span>Native data only: imported tracker history is excluded.</span>;
  }

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
              void update(
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
            <CustomRange
              key={`${period.from}-${period.to}`}
              from={period.from}
              to={period.to}
              onApply={(range) => {
                void update(range, { replace: true });
              }}
            />
          )}
          <SelectField
            label="Product"
            hideLabel
            size="sm"
            value={search.product ?? ALL}
            onChange={(value) => {
              void update({ product: value === null || value === ALL ? undefined : value });
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
              void update({ channel: value === null || value === ALL ? undefined : value });
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
              void update({ partner: value === null || value === ALL ? undefined : Number(value) });
            }}
            options={partnerOptions}
          />
          <CheckboxField
            isSelected={importedIncluded}
            onChange={(selected) => {
              void update({ imported: selected ? undefined : false });
            }}
          >
            Include imported history
          </CheckboxField>
        </div>
      </header>

      {/* Always rendered, so the tiles don't move when the line arrives (§5.3). */}
      <p className="app-metrics-provenance">{provenance}</p>

      {headline}
      <WaitingRow summary={data} search={search} />

      {ordered && !empty && (
        <Trend
          params={params}
          metric={search.chart}
          bucket={search.bucket}
          view={search.view}
          importedIncluded={importedIncluded}
          quietError={summary.isError}
          onChange={(change) => {
            void update(change, { keepDrill: true });
          }}
          onPick={drillPoint}
        />
      )}

      {ordered && search.drill !== undefined && (
        <DrillDown
          params={params}
          metric={search.drill}
          range={{ from: search.dfrom ?? period.from, to: search.dto ?? period.to }}
          openOnly={search.open === true}
          onClose={closeDrill}
        />
      )}
    </div>
  );
}
