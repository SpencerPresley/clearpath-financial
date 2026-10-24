/*
 * My submissions (product-spec): what's waiting on the marketer and why, so nobody has to email "any
 * update?". Sections in the order the marketer acts on them; each row says who has the ball and what's next.
 */
import { useQueries } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';

import { getGetItemQueryOptions, useListItems } from '../../api/generated/items/items';
import type { ItemDetailOut, ItemRowOut } from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { ButtonLink } from '../../ui/ButtonLink';
import { EmptyState } from '../../ui/EmptyState';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { ItemKey } from '../../ui/ItemKey';
import { plural } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonTable } from '../../ui/Skeleton';
import { BUCKETS, NEEDS_DETAIL, waitingOn } from './waitingOn';
import type { WaitingBucket, WaitingOn } from './waitingOn';

export const MINE_PARAMS = { submitted_by_me: true, sort: 'updated', limit: 200 } as const;

/** Key, title, status, why, age, action: one set of widths for every section and the skeleton. */
const COLUMNS = ['7.5rem', '26%', '10.5rem', 'auto', '3.5rem', '9.5rem'] as const;
const SKELETON_COLUMNS = COLUMNS.map((width) => (width === 'auto' ? '1fr' : width));

const ACTION_LABELS = { resubmit: 'Resubmit', new_round: 'Start new round' } as const;

interface Row {
  item: ItemRowOut;
  waiting: WaitingOn;
}

function MineRow({ item, waiting, now }: Row & { now: Date }) {
  return (
    <tr className="app-mine-row">
      <td>
        <ItemKey value={item.key} />
      </td>
      <td className="app-mine-title">
        <Link to="/items/$itemId" params={{ itemId: String(item.id) }} className="app-mine-link">
          {item.title}
        </Link>
      </td>
      <td>
        <StatusBadge status={item.status} />
      </td>
      <td className="app-mine-why" title={waiting.why}>
        {waiting.why}
      </td>
      <td className="app-mine-age">
        <RelativeAge at={item.updated_at} now={now} />
      </td>
      <td className="app-mine-action">
        {waiting.action !== undefined && (
          <ButtonLink
            to="/mine/$itemId/resubmit"
            params={{ itemId: String(item.id) }}
            size="sm"
            aria-label={`${ACTION_LABELS[waiting.action]} ${item.key}`}
          >
            {ACTION_LABELS[waiting.action]}
          </ButtonLink>
        )}
      </td>
    </tr>
  );
}

function MineSection({ label, rows, now }: { label: string; rows: readonly Row[]; now: Date }) {
  return (
    <section aria-label={`${label}, ${plural(rows.length, 'item')}`} className="app-mine-section">
      <h2 className="app-mine-heading">
        {label} <span className="app-mine-count">{rows.length}</span>
      </h2>
      <table className="app-mine-table">
        <colgroup>
          {COLUMNS.map((width, index) => (
            <col key={index} style={width === 'auto' ? undefined : { width }} />
          ))}
        </colgroup>
        <thead className="sr-only">
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Title</th>
            <th scope="col">Status</th>
            <th scope="col">Why</th>
            <th scope="col">Updated</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <MineRow key={row.item.id} {...row} now={now} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function MinePage() {
  const list = useListItems(MINE_PARAMS);
  const rows = list.data?.rows ?? [];

  // The why line for a change request quotes the decision, which only the item detail carries.
  const detailRows = rows.filter((row) => NEEDS_DETAIL.has(row.status));
  const details = useQueries({ queries: detailRows.map((row) => getGetItemQueryOptions(row.id)) });
  const detailById = new Map<number, ItemDetailOut>();
  details.forEach((query, index) => {
    const row = detailRows[index];
    if (row !== undefined && query.data !== undefined) detailById.set(row.id, query.data);
  });

  const now = new Date();
  const grouped = new Map<WaitingBucket, Row[]>();
  for (const item of rows) {
    const waiting = waitingOn(item, detailById.get(item.id));
    grouped.set(waiting.bucket, [...(grouped.get(waiting.bucket) ?? []), { item, waiting }]);
  }

  let body: React.ReactNode;
  if (list.isPending) {
    body = <SkeletonTable rows={6} columns={SKELETON_COLUMNS} label="Loading your submissions" />;
  } else if (list.isError) {
    body = (
      <div className="app-mine-error" role="alert">
        <p className="app-mine-error-title">Couldn&apos;t load your submissions.</p>
        <p className="app-muted">{apiErrorMessage(list.error)}</p>
        <Button
          size="sm"
          onPress={() => {
            void list.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        icon="nav.my_submissions"
        title="Nothing submitted yet"
        action={
          <ButtonLink to="/submit" variant="primary" icon="nav.new_submission">
            New submission
          </ButtonLink>
        }
      >
        Items you submit show here, with who has them and what&apos;s next.
      </EmptyState>
    );
  } else {
    body = BUCKETS.map((bucket) => {
      const bucketRows = grouped.get(bucket.id) ?? [];
      return bucketRows.length === 0 ? null : (
        <MineSection key={bucket.id} label={bucket.label} rows={bucketRows} now={now} />
      );
    });
  }

  return (
    <div className="app-mine">
      <header className="app-mine-header">
        <h1 className="app-page-title">My submissions</h1>
        {rows.length > 0 && (
          <ButtonLink to="/submit" variant="primary" icon="nav.new_submission">
            New submission
          </ButtonLink>
        )}
      </header>
      {body}
    </div>
  );
}
