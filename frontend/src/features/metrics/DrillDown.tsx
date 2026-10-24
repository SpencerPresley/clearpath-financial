/*
 * The items behind a number: GET /metrics/items runs the same computation as the number, so `total` equals
 * it. Imported rows say so and carry their tracker Request ID; every row opens the item.
 */
import { Link } from '@tanstack/react-router';

import { useListMetricItems } from '../../api/generated/metrics/metrics';
import type { GetMetricsSummaryParams, MetricItemOut, MetricName } from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
import { formatDate, OUTCOME_LABELS, plural } from '../../ui/labels';
import { SkeletonTable } from '../../ui/Skeleton';
import { formatHours, formatRounds, rangeLabel } from './format';
import { METRIC_META } from './labels';

const COLUMNS = ['7rem', '1fr', '9.5rem', '11rem', '7rem', '7rem', '6rem'] as const;

function value(metric: MetricName, row: MetricItemOut): string {
  const unit = METRIC_META[metric].unit;
  if (unit === 'hours') return formatHours(row.value);
  if (unit === 'rounds') return formatRounds(row.value).replace(/\.0$/, '');
  return row.outcome === null ? 'Decision' : OUTCOME_LABELS[row.outcome];
}

function Row({ metric, row }: { metric: MetricName; row: MetricItemOut }) {
  const { item } = row;
  return (
    <tr className="app-metric-drill-row">
      <td>
        <ItemKey value={item.key} />
      </td>
      <td className="app-metric-drill-title">
        <Link to="/items/$itemId" params={{ itemId: String(item.id) }} className="app-mine-link">
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
      <td className="app-num">{row.end === null ? 'Open' : formatDate(row.end)}</td>
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
  const title = openOnly ? `${meta.label} · open now` : `${meta.label} · ${rangeLabel(range.from, range.to)}`;
  const data = query.data;

  let body: React.ReactNode;
  if (query.isPending) {
    body = <SkeletonTable rows={4} columns={COLUMNS} label="Loading the items" />;
  } else if (query.isError) {
    body = (
      <div className="app-mine-error" role="alert">
        <p className="app-mine-error-title">Couldn&apos;t load the items.</p>
        <p className="app-muted">{apiErrorMessage(query.error)}</p>
        <Button
          size="sm"
          onPress={() => {
            void query.refetch();
          }}
        >
          Retry
        </Button>
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
    <section className="app-metric-drill" aria-label={title}>
      <header className="app-metric-drill-header">
        <h2 className="app-mine-heading">
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
