/*
 * Low-stakes field edits (tags, notes, risk tier), optimistic with rollback (spec §5.7). The row changes in
 * every cached list and the item detail at once; a failure restores the snapshot and says why in a toast.
 *
 * Permissions mirror the service (backend/reviews/services.py update_item_fields): tags and notes by the
 * submitter or a reviewer; risk tier by reviewers and leads only. The UI hides what the server would refuse.
 */
import { useQueryClient } from '@tanstack/react-query';
import type { QueryClient, QueryKey } from '@tanstack/react-query';
import { useMemo } from 'react';

import {
  getGetItemQueryKey,
  getGetQueueStatsQueryKey,
  getListItemsQueryKey,
  useUpdateItem,
} from '../../api/generated/items/items';
import type { ItemDetailOut, ItemPageOut, ItemRowOut, ItemUpdateIn } from '../../api/generated/model';
import { errorMessage } from '../../ui/errorMessage';
import { canAssign, canClaim, useAssign, useClaim } from './useAssignment';
import type { Viewer } from '../../ui/layout/Viewer';
import { showToast } from '../../ui/toast';
import type { QueueCellContextValue } from './cellContext';
import type { QueuePages } from './useQueueItems';

const LISTS: QueryKey = getListItemsQueryKey().slice(0, 1);

export function canEditRisk(viewer: Viewer): boolean {
  return viewer.roles.includes('reviewer') || viewer.roles.includes('lead');
}

export function canEditFields(viewer: Viewer, row: Pick<ItemRowOut, 'owner'>): boolean {
  return canEditRisk(viewer) || row.owner?.id === viewer.id;
}

type Changes = Partial<Pick<ItemRowOut, 'tags' | 'risk_tier'>> & { notes?: string };

function toChanges(patch: ItemUpdateIn): Changes {
  const changes: Changes = {};
  if (patch.tags !== undefined && patch.tags !== null) changes.tags = patch.tags;
  if (patch.risk_tier !== undefined && patch.risk_tier !== null) changes.risk_tier = patch.risk_tier;
  if (patch.notes !== undefined && patch.notes !== null) changes.notes = patch.notes;
  return changes;
}

function isPages(data: unknown): data is QueuePages {
  return typeof data === 'object' && data !== null && 'pages' in data;
}

function isPage(data: unknown): data is ItemPageOut {
  return typeof data === 'object' && data !== null && 'rows' in data;
}

/** Apply `fn` to item `id` in every cached list (infinite pages and single pages alike). */
export function updateCachedRows(qc: QueryClient, id: number, fn: (row: ItemRowOut) => ItemRowOut) {
  const mapRows = (rows: ItemRowOut[]) => rows.map((row) => (row.id === id ? fn(row) : row));
  for (const [key, data] of qc.getQueriesData({ queryKey: LISTS })) {
    if (isPages(data)) {
      qc.setQueryData<QueuePages>(key, {
        ...data,
        pages: data.pages.map((page) => ({ ...page, rows: mapRows(page.rows) })),
      });
    } else if (isPage(data)) {
      qc.setQueryData<ItemPageOut>(key, { ...data, rows: mapRows(data.rows) });
    }
  }
}

interface Snapshot {
  entries: [QueryKey, unknown][];
}

export function useItemPatch() {
  const qc = useQueryClient();
  return useUpdateItem<unknown, Snapshot>({
    mutation: {
      onMutate: async ({ itemId, data }) => {
        const detailKey = getGetItemQueryKey(itemId);
        await qc.cancelQueries({ queryKey: LISTS });
        await qc.cancelQueries({ queryKey: detailKey });
        const entries: [QueryKey, unknown][] = [
          ...qc.getQueriesData({ queryKey: LISTS }),
          [detailKey, qc.getQueryData(detailKey)],
        ];
        const changes = toChanges(data);
        // Rows carry no notes (ItemRowOut), so only tags and risk tier patch the lists.
        const rowChanges: Partial<ItemRowOut> = {};
        if (changes.tags !== undefined) rowChanges.tags = changes.tags;
        if (changes.risk_tier !== undefined) rowChanges.risk_tier = changes.risk_tier;
        updateCachedRows(qc, itemId, (row) => ({ ...row, ...rowChanges }));
        qc.setQueryData<ItemDetailOut>(detailKey, (old) =>
          old === undefined ? old : { ...old, ...changes },
        );
        return { entries };
      },
      onSuccess: (saved) => {
        updateCachedRows(qc, saved.id, () => saved);
      },
      onError: (error, { itemId }, snapshot) => {
        for (const [key, data] of snapshot?.entries ?? []) qc.setQueryData(key, data);
        const row = snapshot?.entries
          .map(([, data]) => data)
          .flatMap((data) =>
            isPages(data) ? data.pages.flatMap((p) => p.rows) : isPage(data) ? data.rows : [],
          )
          .find((r) => r.id === itemId);
        showToast({
          tone: 'error',
          title: `Couldn't save ${row?.key ?? `CP-${String(itemId)}`}`,
          description: errorMessage(error, 'The change was undone. Try again.'),
        });
      },
      onSettled: (_data, _error, { itemId }) => {
        void qc.invalidateQueries({ queryKey: LISTS });
        void qc.invalidateQueries({ queryKey: getGetQueueStatsQueryKey() });
        void qc.invalidateQueries({ queryKey: getGetItemQueryKey(itemId) });
      },
    },
  });
}

/** What the table's editable cells need for this viewer. */
export function useQueueCells(viewer: Viewer): Omit<QueueCellContextValue, 'now' | 'activeId'> {
  const { mutate } = useItemPatch();
  const { claim } = useClaim();
  const { assign } = useAssign();
  return useMemo(
    () => ({
      canEditRisk: () => canEditRisk(viewer),
      canEditTags: (row: ItemRowOut) => canEditFields(viewer, row),
      save: (row: ItemRowOut, patch: ItemUpdateIn) => {
        mutate({ itemId: row.id, data: patch });
      },
      canClaim: (row: ItemRowOut) => canClaim(viewer, row),
      canAssign: (row: ItemRowOut) => canAssign(viewer, row),
      claim,
      assign,
    }),
    [viewer, mutate, claim, assign],
  );
}
