/*
 * The queue screen (product-spec "Screens": Queue). Composes the counts, views, filters, the table or board,
 * the preview drawer, and the keyboard model. URL search params are the state (search.ts); this component
 * keeps only what isn't worth a URL: the roving row, the selection, and column choices.
 *
 * Every region fails on its own (spec §5.5 partial state): stats, saved views, and later pages show inline
 * errors while the rest keeps working.
 */
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ToggleButton, ToggleButtonGroup } from 'react-aria-components';
import type { Key } from 'react-aria-components';

import { useGetQueueStats, useListSavedViews } from '../../api/generated/items/items';
import type { SavedViewOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { useViewer } from '../../ui/layout/Viewer';
import { Board } from './Board';
import { BulkBar } from './BulkBar';
import {
  ColumnChooser,
  readColumns,
  visibilityFromColumns,
  visibleColumnIds,
  writeColumns,
} from './ColumnChooser';
import type { ColumnVisibility, RowSelection } from './columns';
import { FilterBar, SortMenu } from './FilterBar';
import { queueKeyAction } from './keyboard';
import { PreviewDrawer } from './PreviewDrawer';
import { QueueFooter } from './QueueFooter';
import { QueueSkeleton, QueueTable, rowElementId } from './QueueTable';
import { activeView, hasFilters, toListParams, viewSearch } from './search';
import type { ActiveView, BuiltInViewId, QueueLayout, QueueSearch } from './search';
import { ShortcutsDialog } from './ShortcutsDialog';
import { StatsStrip } from './StatsStrip';
import { useQueueCells } from './useItemPatch';
import { useQueueItems } from './useQueueItems';
import { SavedViewsError, ViewBar } from './ViewBar';

const NO_VIEWS: SavedViewOut[] = [];

/** The drawer shows these, so they step aside while it's open and the triage columns keep their width. */
const DRAWER_HIDDEN: ColumnVisibility = { partner: false, assignee: false, round: false, risk_tier: false };

function EmptyQueue({
  view,
  search,
  onView,
  onClear,
}: {
  view: ActiveView;
  search: QueueSearch;
  onView: (id: BuiltInViewId) => void;
  onClear: () => void;
}) {
  const stats = useGetQueueStats();
  if (search.q !== undefined && search.q !== '') {
    return (
      <EmptyState
        icon="action.search"
        title={`No items match “${search.q}”`}
        action={
          <Button size="sm" onPress={onClear}>
            Clear search and filters
          </Button>
        }
      >
        Search looks at titles and item keys like CP-1042.
      </EmptyState>
    );
  }
  if (view.kind === 'custom' || view.modified) {
    return (
      <EmptyState
        icon="action.filter"
        title="No items match these filters"
        action={
          <Button size="sm" onPress={onClear}>
            Clear filters
          </Button>
        }
      />
    );
  }
  if (view.kind === 'builtin' && view.id === 'mine') {
    const unassigned = stats.data?.unassigned;
    return (
      <EmptyState
        icon="nav.queue"
        title="Nothing assigned to you"
        action={
          unassigned !== undefined && unassigned > 0 ? (
            <Button
              size="sm"
              onPress={() => {
                onView('unassigned');
              }}
            >
              Show unassigned
            </Button>
          ) : undefined
        }
      >
        {unassigned === undefined
          ? undefined
          : unassigned === 0
            ? 'No unassigned items either.'
            : `${String(unassigned)} unassigned ${unassigned === 1 ? 'item' : 'items'}`}
      </EmptyState>
    );
  }
  const copy: Partial<Record<BuiltInViewId, [string, string]>> = {
    unassigned: ['No unassigned items', 'Every item in the queue has a reviewer.'],
    waiting: ['Nothing waiting more than 3 days', 'Every queued item was submitted in the last 3 days.'],
    rereview: [
      'No re-reviews',
      'Approved content comes back here when offer terms change, an approval expires, or drift is found.',
    ],
    active: ['No active items', 'Nothing is submitted, in review, waiting on changes, or up for re-review.'],
  };
  const [title, detail] = (view.kind === 'builtin' ? copy[view.id] : undefined) ?? [
    `No items in ${view.label}`,
    'Nothing matches this view right now.',
  ];
  return (
    <EmptyState icon="nav.queue" title={title}>
      {detail}
    </EmptyState>
  );
}

export function QueuePage() {
  const search = useSearch({ from: '/' });
  const navigate = useNavigate({ from: '/' });
  const viewer = useViewer();
  const cells = useQueueCells(viewer);

  const [columns, setColumns] = useState<ColumnVisibility>(readColumns);
  const [activeId, setActiveId] = useState<number | null>(search.item ?? null);
  const [helpOpen, setHelpOpen] = useState(false);
  /** The item whose drawer should take focus (opened with Enter), as opposed to following j/k. */
  const [focusDrawer, setFocusDrawer] = useState<number | null>(null);

  const listKey = JSON.stringify(toListParams(search));
  const [selection, setSelectionState] = useState<{ key: string; rows: RowSelection }>({
    key: listKey,
    rows: {},
  });
  // Selection belongs to one result set: changing filters starts a fresh one.
  const rowSelection = selection.key === listKey ? selection.rows : {};
  const selectedIds = Object.keys(rowSelection).map(Number);

  const { rows, query } = useQueueItems(search, { enabled: search.layout === 'table' });
  const savedViews = useListSavedViews();
  const view = activeView(search, savedViews.data ?? NO_VIEWS);

  const update = (patch: Partial<QueueSearch>, replace = false) => {
    void navigate({ search: (prev) => ({ ...prev, ...patch }), replace });
  };
  const go = (next: QueueSearch) => {
    void navigate({ search: { ...next, layout: search.layout } });
  };
  const openItem = (id: number | undefined) => {
    update({ item: id }, true);
  };
  const openReview = (id: number) => {
    void navigate({ to: '/items/$itemId', params: { itemId: String(id) } });
  };
  const setColumnsAndSave = (next: ColumnVisibility) => {
    setColumns(next);
    writeColumns(next);
  };
  const setSelectedIds = (ids: number[]) => {
    setSelectionState({
      key: listKey,
      rows: Object.fromEntries(ids.map((id) => [String(id), true as const])),
    });
  };
  const clearToView = () => {
    go(view.kind === 'custom' ? viewSearch('mine') : view.base);
  };

  const focusRow = (id: number) => {
    const el = document.getElementById(rowElementId(id));
    el?.focus();
    el?.scrollIntoView({ block: 'nearest' });
  };

  // Keyboard: one document listener reading the latest state through a ref.
  const handler = useRef<(e: KeyboardEvent) => void>(() => undefined);
  const onKey = (e: KeyboardEvent) => {
    const action = queueKeyAction(e);
    if (action === null) return;
    if (action === 'help') {
      e.preventDefault();
      setHelpOpen(true);
      return;
    }
    if (action === 'close') {
      if (search.item !== undefined) {
        openItem(undefined);
        if (activeId !== null) focusRow(activeId);
      }
      return;
    }
    if (search.layout !== 'table' || rows.length === 0) return;
    const index = rows.findIndex((r) => r.id === activeId);
    if (action === 'next' || action === 'prev') {
      e.preventDefault();
      const nextIndex =
        index === -1 ? 0 : Math.min(rows.length - 1, Math.max(0, index + (action === 'next' ? 1 : -1)));
      const next = rows[nextIndex];
      if (next === undefined) return;
      setActiveId(next.id);
      focusRow(next.id);
      if (search.item !== undefined) {
        setFocusDrawer(null);
        openItem(next.id);
      }
      return;
    }
    const current = rows[index];
    if (current === undefined) return;
    e.preventDefault();
    if (action === 'open') {
      setFocusDrawer(current.id);
      openItem(current.id);
    } else if (action === 'review') {
      openReview(current.id);
    } else {
      const ids = new Set(selectedIds);
      if (ids.has(current.id)) ids.delete(current.id);
      else ids.add(current.id);
      setSelectedIds([...ids]);
    }
  };
  useEffect(() => {
    handler.current = onKey;
  });
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      handler.current(e);
    };
    document.addEventListener('keydown', listener);
    return () => {
      document.removeEventListener('keydown', listener);
    };
  }, []);

  const visibleIds = useMemo(() => visibleColumnIds(columns), [columns]);
  const showBulk = search.layout === 'table' && selectedIds.length > 0;
  const tableColumns = useMemo(
    () => (search.item === undefined ? columns : { ...columns, ...DRAWER_HIDDEN }),
    [columns, search.item],
  );

  let region;
  if (search.layout === 'board') {
    region = <Board search={search} viewer={viewer} onOpen={openItem} />;
  } else if (query.isPending) {
    region = (
      <div className="app-queue-region">
        <QueueSkeleton columnVisibility={tableColumns} />
      </div>
    );
  } else if (query.isError && rows.length === 0) {
    region = (
      <div className="app-queue-region app-queue-error" role="alert">
        <EmptyState
          icon="feedback.error"
          title="Couldn't load the queue"
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
  } else if (rows.length === 0) {
    region = (
      <div className="app-queue-region">
        <EmptyQueue
          view={view}
          search={search}
          onView={(id) => {
            go(viewSearch(id));
          }}
          onClear={clearToView}
        />
      </div>
    );
  } else {
    region = (
      <div className="app-queue-region" aria-busy={query.isPlaceholderData ? 'true' : undefined}>
        <QueueTable
          rows={rows}
          sort={search.sort}
          onSortChange={(sort) => {
            update({ sort });
          }}
          activeId={activeId}
          onActiveChange={setActiveId}
          onOpen={openItem}
          rowSelection={rowSelection}
          onRowSelectionChange={(updater) => {
            const next = typeof updater === 'function' ? updater(rowSelection) : updater;
            setSelectionState({ key: listKey, rows: next });
          }}
          columnVisibility={tableColumns}
          cells={cells}
        />
        <QueueFooter query={query} count={rows.length} />
        {showBulk && (
          <BulkBar viewer={viewer} selectedIds={selectedIds} rows={rows} onSelectionChange={setSelectedIds} />
        )}
      </div>
    );
  }

  return (
    <section className="app-queue" aria-labelledby="queue-title">
      <div className="app-queue-head">
        <h1 id="queue-title" className="app-queue-title">
          Queue
        </h1>
        <StatsStrip
          active={view.kind === 'builtin' && !view.modified ? view.id : undefined}
          onPick={(id) => {
            go(viewSearch(id));
          }}
        />
      </div>
      <div className="app-view-bar">
        <ViewBar
          search={search}
          columns={visibleIds}
          onSelect={(next, cols) => {
            go(next);
            if (cols !== undefined) setColumnsAndSave(visibilityFromColumns(cols));
          }}
        />
        <div className="app-toolbar-end">
          <SortMenu
            sort={search.sort}
            onChange={(sort) => {
              update({ sort });
            }}
          />
          {search.layout === 'table' && <ColumnChooser visibility={columns} onChange={setColumnsAndSave} />}
          <LayoutToggle
            layout={search.layout}
            onChange={(layout) => {
              update({ layout });
            }}
          />
          <IconButton
            icon="action.shortcuts"
            size="sm"
            aria-label="Keyboard shortcuts (?)"
            onPress={() => {
              setHelpOpen(true);
            }}
          />
        </div>
      </div>
      <FilterBar
        search={search}
        hideStatus={search.layout === 'board'}
        isModified={view.kind === 'custom' ? hasFilters(search) : view.modified}
        onChange={(patch) => {
          update(patch);
        }}
        onClear={clearToView}
        trailing={<SavedViewsError />}
      />
      <div className="app-queue-body">
        {region}
        {search.item !== undefined && (
          <PreviewDrawer
            key={search.item}
            itemId={search.item}
            viewer={viewer}
            onClose={() => {
              openItem(undefined);
            }}
            onOpenReview={openReview}
            autoFocus={focusDrawer === search.item}
          />
        )}
      </div>
      <ShortcutsDialog isOpen={helpOpen} onOpenChange={setHelpOpen} />
    </section>
  );
}

function LayoutToggle({
  layout,
  onChange,
}: {
  layout: QueueLayout;
  onChange: (layout: QueueLayout) => void;
}) {
  return (
    <ToggleButtonGroup
      aria-label="Layout"
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={new Set<Key>([layout])}
      onSelectionChange={(keys) => {
        const next = [...keys][0];
        if (next === 'table' || next === 'board') onChange(next);
      }}
      className="app-segmented"
    >
      <ToggleButton id="table" className="app-segmented-item">
        <Icon name="view.table" size={14} />
        Table
      </ToggleButton>
      <ToggleButton id="board" className="app-segmented-item">
        <Icon name="view.board" size={14} />
        Board
      </ToggleButton>
    </ToggleButtonGroup>
  );
}
