/*
 * Queue columns (TanStack Table v9). Module-scope and stable: features and column defs are model inputs, and
 * recreating them per render invalidates the row model (bundled table-core skill, "stable inputs").
 *
 * Sorting is server-owned and limited to the orders `GET /items` supports (queue, oldest, newest, updated,
 * title; backend/reviews/selectors.py _SORTS). Only Title and Age have a header sort; see SORT_CYCLES.
 */
import {
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  createColumnHelper,
  rowSelectionFeature,
  tableFeatures,
} from '@tanstack/react-table';
import type { ColumnSizingState, ColumnVisibilityState, RowSelectionState } from '@tanstack/react-table';

import type { ItemRowOut, ItemSort } from '../../api/generated/model';
import { StatusBadge } from '../../ui/badges';
import { ItemKey } from '../../ui/ItemKey';
import { formatAge } from '../../ui/RelativeAge';
import { useQueueCell } from './cellContext';
import { AssigneeCell } from './AssigneeCell';
import { FindingsCount } from './FindingsCount';
import { CHANNEL_LABEL, PRODUCT_LABEL, REOPEN_REASON_LABEL, roundLabel } from './labels';
import { RiskCell } from './RiskCell';
import { stopRowClick } from './stopRowClick';
import { TagsCell } from './TagsCell';

export const queueFeatures = tableFeatures({
  columnSizingFeature,
  columnResizingFeature,
  columnVisibilityFeature,
  rowSelectionFeature,
});

export type QueueFeatures = typeof queueFeatures;
export type RowSelection = RowSelectionState;
export type ColumnVisibility = ColumnVisibilityState;
export type ColumnSizing = ColumnSizingState;

export const COLUMN_IDS = [
  'select',
  'key',
  'title',
  'status',
  'risk_tier',
  'product',
  'channel',
  'partner',
  'assignee',
  'open_findings',
  'age',
  'round',
  'reopen_reason',
  'tags',
] as const;
export type ColumnId = (typeof COLUMN_IDS)[number];

/** Header text, also the column chooser's labels. `select` has no chooser entry. */
export const COLUMN_LABELS: Record<Exclude<ColumnId, 'select'>, string> = {
  key: 'Item',
  title: 'Title',
  status: 'Status',
  risk_tier: 'Risk',
  product: 'Product',
  channel: 'Channel',
  partner: 'Partner',
  assignee: 'Assignee',
  open_findings: 'Findings',
  age: 'Age',
  round: 'Round',
  reopen_reason: 'Re-review reason',
  tags: 'Tags',
};

/**
 * Hidden until chosen, so the default set fits 1280px without sideways scrolling. Product and channel are in
 * the preview drawer; re-review reason is implied by the Re-review status badge.
 */
export const DEFAULT_COLUMN_VISIBILITY: ColumnVisibility = {
  product: false,
  channel: false,
  reopen_reason: false,
  tags: false,
};

/** Title takes whatever width the other columns leave (never below this), so it isn't resizable itself. */
export const TITLE_MIN_WIDTH = 180;

/** Clicking a sortable header moves to the next server order; the last step returns to queue order. */
export const SORT_CYCLES: Partial<Record<ColumnId, readonly ItemSort[]>> = {
  title: ['title', 'queue'],
  age: ['oldest', 'newest', 'queue'],
};

/** aria-sort for a header under the current server sort. Oldest first = age descending. */
export function ariaSortFor(id: ColumnId, sort: ItemSort): 'ascending' | 'descending' | undefined {
  if (id === 'title' && sort === 'title') return 'ascending';
  if (id === 'age' && sort === 'oldest') return 'descending';
  if (id === 'age' && sort === 'newest') return 'ascending';
  return undefined;
}

export function nextSort(id: ColumnId, sort: ItemSort): ItemSort {
  const cycle = SORT_CYCLES[id];
  if (cycle === undefined) return sort;
  const at = cycle.indexOf(sort);
  return cycle[(at + 1) % cycle.length] ?? 'queue';
}

function Muted({ children }: { children: string }) {
  return <span className="text-muted">{children}</span>;
}

function AgeCell({ at }: { at: string }) {
  const { now } = useQueueCell();
  const date = new Date(at);
  return (
    <time className="app-age" dateTime={date.toISOString()} title={date.toLocaleString('en-US')}>
      {formatAge(date, now ?? new Date())}
    </time>
  );
}

const helper = createColumnHelper<QueueFeatures, ItemRowOut>();

export const queueColumns = helper.columns([
  helper.display({
    id: 'select',
    size: 36,
    enableResizing: false,
    enableHiding: false,
    header: ({ table }) => (
      <label className="app-check-hit">
        <input
          type="checkbox"
          className="app-check"
          aria-label="Select all loaded items"
          checked={table.getIsAllRowsSelected()}
          ref={(el) => {
            if (el) el.indeterminate = table.getIsSomeRowsSelected() && !table.getIsAllRowsSelected();
          }}
          onChange={table.getToggleAllRowsSelectedHandler()}
        />
      </label>
    ),
    cell: ({ row }) => (
      // The label fills the cell so the whole 36px square selects (a near miss would open the preview).
      <label className="app-check-hit" onClick={stopRowClick}>
        <input
          type="checkbox"
          className="app-check"
          aria-label={`Select ${row.original.key}`}
          checked={row.getIsSelected()}
          onClick={(event) => {
            event.stopPropagation();
            row.getToggleSelectedHandler()(event);
          }}
          onChange={() => {
            /* handled on click, which carries Shift for range selection */
          }}
        />
      </label>
    ),
  }),
  helper.accessor('key', {
    id: 'key',
    header: COLUMN_LABELS.key,
    size: 76,
    minSize: 72,
    cell: ({ row }) => <ItemKey value={row.original.key} copyable={false} />,
  }),
  helper.accessor('title', {
    id: 'title',
    header: COLUMN_LABELS.title,
    size: TITLE_MIN_WIDTH,
    minSize: TITLE_MIN_WIDTH,
    enableResizing: false,
    cell: ({ row }) => (
      <span className="app-cell-title" title={row.original.title}>
        {row.original.title}
      </span>
    ),
  }),
  helper.accessor('status', {
    id: 'status',
    header: COLUMN_LABELS.status,
    size: 168,
    minSize: 44,
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  }),
  helper.accessor('risk_tier', {
    id: 'risk_tier',
    header: COLUMN_LABELS.risk_tier,
    size: 96,
    minSize: 72,
    cell: ({ row }) => <RiskCell row={row.original} />,
  }),
  helper.accessor('product', {
    id: 'product',
    header: COLUMN_LABELS.product,
    size: 124,
    minSize: 72,
    cell: ({ row }) => PRODUCT_LABEL[row.original.product],
  }),
  helper.accessor('channel', {
    id: 'channel',
    header: COLUMN_LABELS.channel,
    size: 120,
    minSize: 72,
    cell: ({ row }) => CHANNEL_LABEL[row.original.channel],
  }),
  helper.accessor('partner', {
    id: 'partner',
    header: COLUMN_LABELS.partner,
    size: 120,
    minSize: 72,
    cell: ({ row }) => row.original.partner?.name ?? <Muted>—</Muted>,
  }),
  helper.accessor('assignee', {
    id: 'assignee',
    header: COLUMN_LABELS.assignee,
    size: 140,
    minSize: 80,
    cell: ({ row }) => <AssigneeCell row={row.original} />,
  }),
  helper.accessor('open_findings_count', {
    id: 'open_findings',
    header: COLUMN_LABELS.open_findings,
    size: 76,
    minSize: 64,
    cell: ({ row }) => <FindingsCount count={row.original.open_findings_count} />,
  }),
  helper.accessor('submitted_at', {
    id: 'age',
    header: COLUMN_LABELS.age,
    size: 56,
    minSize: 56,
    cell: ({ row }) => <AgeCell at={row.original.submitted_at} />,
  }),
  helper.accessor('round', {
    id: 'round',
    header: COLUMN_LABELS.round,
    size: 56,
    minSize: 52,
    cell: ({ row }) => <span className="app-figure">{roundLabel(row.original.round)}</span>,
  }),
  helper.accessor('reopen_reason', {
    id: 'reopen_reason',
    header: COLUMN_LABELS.reopen_reason,
    size: 140,
    minSize: 80,
    cell: ({ row }) =>
      row.original.reopen_reason === null ? null : REOPEN_REASON_LABEL[row.original.reopen_reason],
  }),
  helper.accessor('tags', {
    id: 'tags',
    header: COLUMN_LABELS.tags,
    size: 180,
    minSize: 96,
    cell: ({ row }) => <TagsCell row={row.original} />,
  }),
]);
