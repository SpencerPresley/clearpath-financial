/*
 * The items behind a number: GET /metrics/items runs the same computation as the number, so `total` equals
 * it. Imported rows say so and carry their tracker Request ID; every row opens the item. The heading takes focus
 * when the list opens (it renders below the trend), and closing returns focus to whatever opened it.
 */
import { Link } from '@tanstack/react-router';
import { useEffect, useRef } from 'react';

import { useListMetricItems } from '../../api/generated/metrics/metrics';
import type {
  GetMetricsSummaryParams,
  ItemStatus,
  MetricItemOut,
  MetricName,
} from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
import { formatDate, OUTCOME_LABELS, plural } from '../../ui/labels';
import { SkeletonTable } from '../../ui/Skeleton';
import { formatHours, formatRounds, rangeLabel } from './format';
import { METRIC_META } from './labels';
import { DRILL_ID } from './MetricTiles';
import { isServerError } from './retry';

const COLUMNS = ['7rem', '1fr', '9.5rem', '11rem', '7rem', '7rem', '6rem'] as const;

function value(metric: MetricName, row: MetricItemOut): string {
  const unit = METRIC_META[metric].unit;
  if (unit === 'hours') return formatHours(row.value);
  if (unit === 'rounds') return formatRounds(row.value).replace(/\.0$/, '');
  return row.outcome === null ? 'Decision' : OUTCOME_LABELS[row.outcome];
}

/** Why a fix-live clock is still running: content pulled but not yet confirmed down, or still in re-review. */
function stillOpen(status: ItemStatus): string {
  return status === 'withdrawn' || status === 'rejected' ? 'Takedown unconfirmed' : 'In re-review';
}

function Row({ metric, row }: { metric: MetricName; row: MetricItemOut }) {
  const { item } = row;
  return (
    <tr className="app-metric-drill-row">
      <td>
        <ItemKey value={item.key} />
      </td>
      <td className="app-metric-drill-title">
        <Link
          to="/items/$itemId"
          params={{ itemId: String(item.id) }}
          className="app-mine-link"
          title={item.title}
        >
          {item.title}
        </Link>
      </td>
      <td>
        <StatusBadge status={item.status} />
      </td>
      <td className="app-muted">
        {row.source === 'imported' ? `Imported · ${item.legacy_ref ?? 'tracker'}` : 'Native'}
      </td>
      <td className="app-num">{formatDate(row.start)}</td>
      <td className="app-num">{row.end === null ? stillOpen(item.status) : formatDate(row.end)}</td>
      <td className="app-num app-metric-drill-value">{value(metric, row)}</td>
    </tr>
  );
}

export function DrillDown({
  params,
  metric,
  range,
  openOnly,
  onClose,
}: {
  params: GetMetricsSummaryParams;
  metric: MetricName;
  /** A bucket's range, or the whole period. */
  range: { from: string; to: string };
  openOnly: boolean;
  onClose: () => void;
}) {
  const meta = METRIC_META[metric];
  const query = useListMetricItems({
    ...params,
    period_from: range.from,
    period_to: range.to,
    metric,
    ...(openOnly && { open_only: true }),
  });
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.scrollIntoView({ block: 'nearest' });
    heading.current?.focus({ preventScroll: true });
  }, [metric, openOnly, range.from, range.to]);
  const title = openOnly
    ? `${meta.label} · re-reviews open now`
    : `${meta.label} · ${rangeLabel(range.from, range.to)}`;
  const data = query.data;

  let body: React.ReactNode;
  if (query.isPending) {
    body = <SkeletonTable rows={4} columns={COLUMNS} label="Loading the items" />;
  } else if (query.isError) {
    body = (
      <div className="app-mine-error" role="alert">
        <p className="app-mine-error-title">Couldn&apos;t load the items.</p>
        <p className="app-muted">{apiErrorMessage(query.error)}</p>
        {isServerError(query.error) && (
          <Button
            size="sm"
            onPress={() => {
              void query.refetch();
            }}
          >
            Retry
          </Button>
        )}
      </div>
    );
  } else if (query.data.rows.length === 0) {
    body = <p className="app-muted">Nothing behind this number for these filters.</p>;
  } else {
    body = (
      <table className="app-mine-table app-metric-drill-table">
        <colgroup>
          {COLUMNS.map((width, index) => (
            <col key={index} style={width === '1fr' ? undefined : { width }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Title</th>
            <th scope="col">Status</th>
            <th scope="col">Source</th>
            <th scope="col" className="app-num">
              {openOnly ? 'Sent back' : 'Started'}
            </th>
            <th scope="col" className="app-num">
              Ended
            </th>
            <th scope="col" className="app-num">
              {meta.unit === 'decisions' ? 'Outcome' : openOnly ? 'Open for' : 'Took'}
            </th>
          </tr>
        </thead>
        <tbody>
          {query.data.rows.map((row, index) => (
            <Row key={`${String(row.item.id)}-${String(index)}`} metric={metric} row={row} />
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section id={DRILL_ID} className="app-metric-drill" aria-label={title}>
      <header className="app-metric-drill-header">
        <h2 ref={heading} tabIndex={-1} className="app-mine-heading app-metric-drill-heading">
          {title}
          {data !== undefined && (
            <span className="app-mine-count">
              {data.rows.length < data.total
                ? `Largest ${String(data.rows.length)} of ${String(data.total)}`
                : openOnly
                  ? plural(data.total, 'open re-review')
                  : plural(data.total, meta.noun[0], meta.noun[1])}
            </span>
          )}
        </h2>
        <IconButton icon="action.close" aria-label="Close the item list" onPress={onClose} />
      </header>
      {body}
    </section>
  );
}
