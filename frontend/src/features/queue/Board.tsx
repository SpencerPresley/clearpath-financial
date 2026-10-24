/*
 * Board view (decisions.md "Queue views"; product-spec "Board view"). Columns: Submitted · In review ·
 * Changes requested · Needs re-review · Approved (14 days). The only move is Submitted → In review ("claim"),
 * by drag (React Aria drag and drop, keyboard included) or the card's Claim button. Every other card press
 * opens the item. Gated moves (to Approved, say) aren't offered: they need a decision with a reason.
 *
 * Columns are the status dimension, so the board ignores the Status filter; every other filter applies.
 */
import { useQueryClient } from '@tanstack/react-query';
import type { DropItem } from 'react-aria-components';
import { Button as AriaButton, GridList, GridListItem, useDragAndDrop } from 'react-aria-components';

import {
  getGetQueueStatsQueryKey,
  getListItemsQueryKey,
  useClaimItem,
  useListItems,
} from '../../api/generated/items/items';
import type { ItemRowOut, ItemStatus } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { ItemKey } from '../../ui/ItemKey';
import type { Viewer } from '../../ui/layout/Viewer';
import { formatAge } from '../../ui/RelativeAge';
import { showToast } from '../../ui/toast';
import { FindingsCount } from './FindingsCount';
import { toListParams } from './search';
import type { QueueSearch } from './search';

export const BOARD_LIMIT = 200;
const ITEM_TYPE = 'application/x-clearpath-item';

type ColumnId = 'submitted' | 'in_review' | 'changes_requested' | 'needs_rereview' | 'approved';

export const BOARD_COLUMNS: readonly { id: ColumnId; label: string }[] = [
  { id: 'submitted', label: 'Submitted' },
  { id: 'in_review', label: 'In review' },
  { id: 'changes_requested', label: 'Changes requested' },
  { id: 'needs_rereview', label: 'Needs re-review' },
  { id: 'approved', label: 'Approved (14 days)' },
];

const ACTIVE_STATUSES: ItemStatus[] = ['submitted', 'in_review', 'changes_requested', 'needs_rereview'];
const EMPTY: ItemRowOut[] = [];

function Card({
  row,
  now,
  claimable,
  onClaim,
}: {
  row: ItemRowOut;
  now: Date;
  claimable: boolean;
  onClaim: (row: ItemRowOut) => void;
}) {
  return (
    <div className="app-card-body">
      <div className="app-card-top">
        {claimable && (
          <AriaButton slot="drag" className="app-card-drag" aria-label={`Drag ${row.key} to In review`}>
            <Icon name="action.drag" size={14} />
          </AriaButton>
        )}
        <ItemKey value={row.key} copyable={false} />
        <time
          className="app-age ml-auto"
          dateTime={row.submitted_at}
          title={new Date(row.submitted_at).toLocaleString('en-US')}
        >
          {formatAge(new Date(row.submitted_at), now)}
        </time>
      </div>
      <p className="app-card-title">{row.title}</p>
      <div className="app-card-meta">
        <span className="truncate">{row.partner?.name ?? 'No partner'}</span>
        <span aria-hidden="true">·</span>
        <span className="truncate">{row.assignee?.name ?? 'Unassigned'}</span>
        <span className="ml-auto">
          <FindingsCount count={row.open_findings_count} />
        </span>
      </div>
      {claimable && (
        <Button
          size="sm"
          className="app-card-claim"
          aria-label={`Claim ${row.key}`}
          onPress={() => {
            onClaim(row);
          }}
        >
          Claim
        </Button>
      )}
    </div>
  );
}

export interface BoardProps {
  search: QueueSearch;
  viewer: Viewer;
  onOpen: (id: number) => void;
}

export function Board({ search, viewer, onOpen }: BoardProps) {
  const qc = useQueryClient();
  const canClaim = viewer.roles.includes('reviewer') || viewer.roles.includes('lead');
  const base = toListParams({ ...search, status: undefined }, { limit: BOARD_LIMIT });
  const active = useListItems({ ...base, status: ACTIVE_STATUSES });
  const approved = useListItems({ ...base, status: ['approved'], approved_within_days: 14, sort: 'updated' });
  const claim = useClaimItem();
  const now = new Date();

  const doClaim = (row: Pick<ItemRowOut, 'id' | 'key'>) => {
    claim.mutate(
      { itemId: row.id },
      {
        onSuccess: () => {
          showToast({ title: `Claimed ${row.key}` });
        },
        onError: (error) => {
          showToast({
            tone: 'error',
            title: `Couldn't claim ${row.key}`,
            description: errorMessage(error, 'It may have been claimed already. Reload and try again.'),
          });
        },
        onSettled: () => {
          void qc.invalidateQueries({ queryKey: getListItemsQueryKey().slice(0, 1) });
          void qc.invalidateQueries({ queryKey: getGetQueueStatsQueryKey() });
        },
      },
    );
  };

  const dropClaim = async (items: DropItem[]) => {
    for (const item of items) {
      if (item.kind === 'text' && item.types.has(ITEM_TYPE)) {
        const id = Number(await item.getText(ITEM_TYPE));
        if (Number.isInteger(id)) doClaim({ id, key: `CP-${String(id)}` });
      }
    }
  };

  const submittedDnd = useDragAndDrop<ItemRowOut>({
    isDisabled: !canClaim,
    getItems: (keys) =>
      [...keys].map((key) => ({ [ITEM_TYPE]: String(key), 'text/plain': `CP-${String(key)}` })),
  });
  const inReviewDnd = useDragAndDrop<ItemRowOut>({
    isDisabled: !canClaim,
    acceptedDragTypes: [ITEM_TYPE],
    getDropOperation: (_target, types) => (types.has(ITEM_TYPE) ? 'move' : 'cancel'),
    onRootDrop: (e) => {
      void dropClaim(e.items);
    },
    onItemDrop: (e) => {
      void dropClaim(e.items);
    },
  });

  const query = (id: ColumnId) => (id === 'approved' ? approved : active);
  const rowsFor = (id: ColumnId) =>
    id === 'approved'
      ? (approved.data?.rows ?? EMPTY)
      : (active.data?.rows ?? EMPTY).filter((r) => r.status === id);
  const truncated = active.data?.next_cursor != null || approved.data?.next_cursor != null;

  return (
    <div className="app-board-wrap">
      <div className="app-board">
        {BOARD_COLUMNS.map((column) => {
          const q = query(column.id);
          const rows = rowsFor(column.id);
          const headingId = `board-${column.id}`;
          return (
            <section key={column.id} className="app-board-col" aria-labelledby={headingId}>
              <header className="app-board-col-head">
                <h2 id={headingId} className="app-board-col-title">
                  {column.label}
                </h2>
                {q.data !== undefined && <span className="app-figure text-muted">{rows.length}</span>}
              </header>
              {q.isPending ? (
                <div className="app-board-list" aria-busy="true" aria-label={`Loading ${column.label}`}>
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="app-card app-card-skeleton" aria-hidden="true">
                      <span className="app-skeleton w-16" />
                      <span className="app-skeleton w-4/5" />
                      <span className="app-skeleton w-1/2" />
                    </div>
                  ))}
                </div>
              ) : q.isError ? (
                <div className="app-board-list" role="alert">
                  <p className="app-inline-error">
                    {errorMessage(q.error, `Couldn't load ${column.label}.`)}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    onPress={() => {
                      void q.refetch();
                    }}
                  >
                    Retry
                  </Button>
                </div>
              ) : (
                <GridList
                  aria-label={column.label}
                  items={rows}
                  className="app-board-list"
                  onAction={(key) => {
                    onOpen(Number(key));
                  }}
                  dragAndDropHooks={
                    column.id === 'submitted'
                      ? submittedDnd.dragAndDropHooks
                      : column.id === 'in_review'
                        ? inReviewDnd.dragAndDropHooks
                        : undefined
                  }
                  renderEmptyState={() => <p className="app-board-empty">No items</p>}
                >
                  {(row) => (
                    <GridListItem id={row.id} textValue={`${row.key} ${row.title}`} className="app-card">
                      <Card
                        row={row}
                        now={now}
                        claimable={canClaim && column.id === 'submitted'}
                        onClaim={doClaim}
                      />
                    </GridListItem>
                  )}
                </GridList>
              )}
            </section>
          );
        })}
      </div>
      {truncated && (
        <p className="app-board-note">
          {`Showing the first ${String(BOARD_LIMIT)} items per group. Narrow the filters or use the table for the rest.`}
        </p>
      )}
    </div>
  );
}
