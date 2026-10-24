/*
 * "Approved to run": every item whose current status is approved, legacy imports included, as a dense table.
 * Each title opens the item; each row has its evidence pack. Keyset pages append below (partial state: a failed
 * later page keeps the rows already shown).
 */
import { Link } from '@tanstack/react-router';

import type { ItemRowOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { ItemKey } from '../../ui/ItemKey';
import { CHANNEL_LABELS, formatDate, plural, PRODUCT_LABELS } from '../../ui/labels';
import { EvidencePackAction } from './EvidencePackAction';
import { hasFilters } from './search';
import type { LibrarySearch } from './search';
import type { LibraryItemsQuery } from './useLibraryItems';

/** Key, title, product, channel, partner, planned run, evidence pack. Title takes the rest. */
const COLUMNS = [
  { id: 'key', label: 'Item', width: '5.5rem' },
  { id: 'title', label: 'Title', width: undefined },
  { id: 'product', label: 'Product', width: '8.5rem' },
  { id: 'channel', label: 'Channel', width: '7rem' },
  { id: 'partner', label: 'Partner', width: '7.5rem' },
  { id: 'run', label: 'Planned run', width: '10.5rem' },
  { id: 'pack', label: 'Evidence pack', width: '7.5rem' },
] as const;

const TITLE_MIN = 240;
/** Fits the 1280px layout (1014px for the table) without sideways scrolling. */
const MIN_WIDTH = TITLE_MIN + 46.5 * 16;

function shortDate(value: string, withYear: boolean): string {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString(
        'en-US',
        withYear ? { month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' },
      );
}

/** "Nov 1 – Dec 31, 2026", "From Oct 1, 2026", or an em dash. */
export function plannedRun(first: string | null, last: string | null): string {
  if (first === null && last === null) return '—';
  if (first !== null && last !== null) {
    if (first.slice(0, 4) === last.slice(0, 4))
      return `${shortDate(first, false)} – ${shortDate(last, true)}`;
    // Across a year end, short years keep it inside the column: "Nov 15 '26 – Jan 15 '27".
    const year = (d: string) => `'${d.slice(2, 4)}`;
    return `${shortDate(first, false)} ${year(first)} – ${shortDate(last, false)} ${year(last)}`;
  }
  if (first !== null) return `From ${formatDate(first)}`;
  return `Until ${formatDate(last ?? '')}`;
}

function Colgroup() {
  return (
    <colgroup>
      {COLUMNS.map((c) => (
        <col key={c.id} style={c.width === undefined ? undefined : { width: c.width }} />
      ))}
    </colgroup>
  );
}

function Head() {
  return (
    <thead>
      <tr>
        {COLUMNS.map((c) => (
          <th key={c.id} className="app-th" scope="col">
            <span className="app-th-label">{c.label}</span>
          </th>
        ))}
      </tr>
    </thead>
  );
}

function Row({ row }: { row: ItemRowOut }) {
  const product = PRODUCT_LABELS[row.product];
  const channel = CHANNEL_LABELS[row.channel];
  return (
    <tr className="app-tr app-library-row">
      <td className="app-td">
        <ItemKey value={row.key} copyable={false} />
      </td>
      <td className="app-td">
        <span className="app-library-title">
          <Link
            to="/items/$itemId"
            params={{ itemId: String(row.id) }}
            className="app-library-link"
            title={row.title}
          >
            {row.title}
          </Link>
          {row.is_legacy && <span className="app-badge app-badge-outline">Legacy</span>}
        </span>
      </td>
      <td className="app-td" title={product}>
        {product}
      </td>
      <td className="app-td" title={channel}>
        {channel}
      </td>
      <td className="app-td" title={row.partner?.name}>
        {row.partner?.name ?? <span className="text-muted">—</span>}
      </td>
      <td className="app-td app-figure">{plannedRun(row.planned_first_run, row.planned_last_run)}</td>
      <td className="app-td">
        <EvidencePackAction itemId={row.id} itemKey={row.key} isLegacy={row.is_legacy} compact />
      </td>
    </tr>
  );
}

export function ApprovedSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading the library" aria-busy="true">
      <table className="app-table" aria-hidden="true" style={{ minWidth: MIN_WIDTH }}>
        <Colgroup />
        <Head />
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r} className="app-tr">
              {COLUMNS.map((c, i) => (
                <td key={c.id} className="app-td">
                  <span
                    className="app-skeleton"
                    style={{ width: `${String(45 + ((r * 17 + i * 29) % 45))}%` }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Footer({ query, count }: { query: LibraryItemsQuery; count: number }) {
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = query;
  if (isFetchNextPageError) {
    return (
      <div className="app-table-footer" role="alert">
        <Icon name="feedback.error" className="text-status-error-soft-content" />
        <span>{errorMessage(query.error, "Couldn't load more items. Try again.")}</span>
        <Button
          size="sm"
          icon="action.reload"
          onPress={() => {
            void fetchNextPage();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }
  return (
    <div className="app-table-footer">
      <span className="app-figure">
        {hasNextPage ? `${plural(count, 'item')} loaded` : `${plural(count, 'item')} approved to run`}
      </span>
      {hasNextPage && (
        <Button
          size="sm"
          variant="ghost"
          isDisabled={isFetchingNextPage}
          onPress={() => {
            void fetchNextPage();
          }}
        >
          {isFetchingNextPage ? 'Loading…' : 'Load more'}
        </Button>
      )}
    </div>
  );
}

export function ApprovedList({
  search,
  rows,
  query,
  onClear,
  onPrecedents,
}: {
  search: LibrarySearch;
  rows: ItemRowOut[];
  query: LibraryItemsQuery;
  onClear: () => void;
  onPrecedents: () => void;
}) {
  if (query.isPending) {
    return (
      <div className="app-library-region">
        <ApprovedSkeleton />
      </div>
    );
  }
  if (query.isError && rows.length === 0) {
    return (
      <div className="app-library-region" role="alert">
        <EmptyState
          icon="feedback.error"
          title="Couldn't load the library"
          action={
            <Button
              size="sm"
              icon="action.reload"
              onPress={() => {
                void query.refetch();
              }}
            >
              Retry
            </Button>
          }
        >
          {errorMessage(query.error, 'Check your connection and try again.')}
        </EmptyState>
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="app-library-region">
        {hasFilters(search) ? (
          <EmptyState
            icon="action.filter"
            title="No approved items match these filters"
            action={
              <Button size="sm" onPress={onClear}>
                Clear filters
              </Button>
            }
          >
            Lapsed approvals aren&apos;t here; precedent search covers every approval ever given.
          </EmptyState>
        ) : (
          <EmptyState
            icon="nav.library"
            title="Nothing is approved to run"
            action={
              <Button size="sm" icon="action.search" onPress={onPrecedents}>
                Search precedents
              </Button>
            }
          >
            Items appear here once approved. Expired and re-review items are still searchable as precedents.
          </EmptyState>
        )}
      </div>
    );
  }
  return (
    <div className="app-library-region" aria-busy={query.isPlaceholderData ? 'true' : undefined}>
      <table className="app-table" aria-label="Approved to run" style={{ minWidth: MIN_WIDTH }}>
        <Colgroup />
        <Head />
        <tbody>
          {rows.map((row) => (
            <Row key={row.id} row={row} />
          ))}
        </tbody>
      </table>
      <Footer query={query} count={rows.length} />
    </div>
  );
}
