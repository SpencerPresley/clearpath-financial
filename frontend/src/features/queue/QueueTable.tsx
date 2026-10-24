/*
 * The queue table: native <table> semantics, TanStack Table v9 for column sizing/resizing, visibility, and
 * row selection. Rows are a roving tab stop (one Tab into the list, then j/k; see keyboard.ts), so cells hold
 * no extra tab stops except deliberate inline-edit controls.
 */
import { useTable } from '@tanstack/react-table';
import type { OnChangeFn } from '@tanstack/react-table';
import { useMemo, useState } from 'react';

import type { ItemRowOut, ItemSort } from '../../api/generated/model';
import { cx } from '../../ui/cx';
import { Icon } from '../../ui/Icon';
import { QueueCellContext, READ_ONLY_CELLS } from './cellContext';
import type { QueueCellContextValue } from './cellContext';
import { ariaSortFor, COLUMN_LABELS, nextSort, queueColumns, queueFeatures, SORT_CYCLES } from './columns';
import type { ColumnId, ColumnSizing, ColumnVisibility, RowSelection } from './columns';

export const SIZES_KEY = 'clearpath.queue.columnSizes';

function readSizes(): ColumnSizing {
  try {
    const raw = window.localStorage.getItem(SIZES_KEY);
    const parsed: unknown = raw === null ? {} : JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter((e): e is [string, number] => typeof e[1] === 'number'),
    );
  } catch {
    return {}; // blocked storage or bad JSON: default widths
  }
}

function writeSizes(sizes: ColumnSizing) {
  try {
    window.localStorage.setItem(SIZES_KEY, JSON.stringify(sizes));
  } catch {
    // storage blocked: widths last for this page view
  }
}

export function rowElementId(id: number): string {
  return `queue-row-${String(id)}`;
}

export interface QueueTableProps {
  rows: ItemRowOut[];
  sort: ItemSort;
  onSortChange: (sort: ItemSort) => void;
  /** The row holding the roving tab stop (and the drawer, when open). */
  activeId: number | null;
  onActiveChange: (id: number) => void;
  onOpen: (id: number) => void;
  rowSelection: RowSelection;
  onRowSelectionChange: OnChangeFn<RowSelection>;
  columnVisibility: ColumnVisibility;
  /** Shared clock for ages; defaults to render time. */
  now?: Date;
  cells?: Omit<QueueCellContextValue, 'now' | 'activeId'>;
}

const noop = () => undefined;

export function QueueTable({
  rows,
  sort,
  onSortChange,
  activeId,
  onActiveChange,
  onOpen,
  rowSelection,
  onRowSelectionChange,
  columnVisibility,
  now,
  cells = READ_ONLY_CELLS,
}: QueueTableProps) {
  const [columnSizing, setColumnSizing] = useState<ColumnSizing>(readSizes);

  const onColumnSizingChange: OnChangeFn<ColumnSizing> = (updater) => {
    setColumnSizing((old) => {
      const next = typeof updater === 'function' ? updater(old) : updater;
      writeSizes(next);
      return next;
    });
  };

  const table = useTable({
    features: queueFeatures,
    columns: queueColumns,
    data: rows,
    getRowId: (row) => String(row.id),
    state: { rowSelection, columnVisibility, columnSizing },
    onRowSelectionChange,
    onColumnVisibilityChange: noop,
    onColumnSizingChange,
    columnResizeMode: 'onChange',
  });

  const headers = table.getHeaderGroups()[0]?.headers ?? [];
  const tabStop = activeId !== null && rows.some((r) => r.id === activeId) ? activeId : rows[0]?.id;
  const cellContext = useMemo(() => ({ ...cells, now, activeId: tabStop }), [cells, now, tabStop]);

  return (
    <QueueCellContext value={cellContext}>
      <table className="app-table" aria-label="Queue" style={{ minWidth: table.getTotalSize() }}>
        <colgroup>
          {headers.map((header) => (
            <col key={header.id} style={{ width: header.getSize() }} />
          ))}
          <col />
        </colgroup>
        <thead>
          <tr>
            {headers.map((header) => {
              const id = header.column.id as ColumnId;
              const label = id === 'select' ? null : COLUMN_LABELS[id];
              const ariaSort = ariaSortFor(id, sort);
              const sortable = SORT_CYCLES[id] !== undefined;
              return (
                <th
                  key={header.id}
                  scope="col"
                  className="app-th"
                  aria-sort={ariaSort}
                  data-column={id}
                  data-resizing={header.column.getIsResizing() ? 'true' : undefined}
                >
                  {label === null ? (
                    <table.FlexRender header={header} />
                  ) : sortable ? (
                    <button
                      type="button"
                      className="app-th-sort"
                      onClick={() => {
                        onSortChange(nextSort(id, sort));
                      }}
                    >
                      <span>{label}</span>
                      <Icon
                        name={
                          ariaSort === 'ascending'
                            ? 'sort.ascending'
                            : ariaSort === 'descending'
                              ? 'sort.descending'
                              : 'sort.none'
                        }
                        size={12}
                        className={cx('app-th-sort-icon', ariaSort === undefined && 'opacity-0')}
                      />
                    </button>
                  ) : (
                    <span className="app-th-label">{label}</span>
                  )}
                  {header.column.getCanResize() && (
                    // Pointer-only affordance; double-click restores the default width.
                    <div
                      aria-hidden="true"
                      className="app-th-resize"
                      onMouseDown={header.getResizeHandler()}
                      onTouchStart={header.getResizeHandler()}
                      onDoubleClick={() => {
                        header.column.resetSize();
                      }}
                    />
                  )}
                </th>
              );
            })}
            <th aria-hidden="true" className="app-th app-th-filler" />
          </tr>
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const item = row.original;
            return (
              <tr
                key={row.id}
                id={rowElementId(item.id)}
                className="app-tr"
                data-row-id={item.id}
                tabIndex={item.id === tabStop ? 0 : -1}
                data-active={item.id === activeId ? 'true' : undefined}
                data-selected={row.getIsSelected() ? 'true' : undefined}
                data-rereview={item.reopen_reason === null ? undefined : 'true'}
                onFocus={(event) => {
                  if (event.target === event.currentTarget) onActiveChange(item.id);
                }}
                onClick={() => {
                  onActiveChange(item.id);
                  onOpen(item.id);
                }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="app-td" data-column={cell.column.id}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
                <td aria-hidden="true" className="app-td" />
              </tr>
            );
          })}
        </tbody>
      </table>
    </QueueCellContext>
  );
}
