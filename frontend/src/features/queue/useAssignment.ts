/*
 * Taking and handing off items (backend/reviews/api.py claim_item, assign_item):
 * - Claim: a reviewer (or lead) takes an unassigned submitted item; it moves to in review, assigned to them.
 * - Assign: a lead or admin assigns any item; a reviewer can hand off an item assigned to them.
 * Neither is optimistic: the server decides (an item can be claimed by someone else first), so the row updates
 * from the refetch and a failure says what happened.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import {
  getGetItemQueryKey,
  getGetQueueStatsQueryKey,
  getListItemsQueryKey,
  useAssignItem,
  useClaimItem,
} from '../../api/generated/items/items';
import type { ItemRowOut } from '../../api/generated/model';
import { errorMessage } from '../../ui/errorMessage';
import type { Viewer } from '../../ui/layout/Viewer';
import { showToast } from '../../ui/toast';

type RowRef = Pick<ItemRowOut, 'id' | 'key'>;

export function canClaimRole(viewer: Viewer): boolean {
  return viewer.roles.includes('reviewer') || viewer.roles.includes('lead');
}

export function canClaim(viewer: Viewer, row: Pick<ItemRowOut, 'status' | 'assignee'>): boolean {
  return canClaimRole(viewer) && row.status === 'submitted' && row.assignee === null;
}

export function canAssign(viewer: Viewer, row: Pick<ItemRowOut, 'assignee'>): boolean {
  if (viewer.roles.includes('lead') || viewer.roles.includes('admin')) return true;
  return viewer.roles.includes('reviewer') && row.assignee?.id === viewer.id;
}

function useSettle() {
  const qc = useQueryClient();
  return useCallback(
    (id: number) => {
      void qc.invalidateQueries({ queryKey: getListItemsQueryKey().slice(0, 1) });
      void qc.invalidateQueries({ queryKey: getGetQueueStatsQueryKey() });
      void qc.invalidateQueries({ queryKey: getGetItemQueryKey(id) });
    },
    [qc],
  );
}

export function useClaim() {
  const { mutate, isPending } = useClaimItem();
  const settle = useSettle();
  const claim = useCallback(
    (row: RowRef) => {
      mutate(
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
            settle(row.id);
          },
        },
      );
    },
    [mutate, settle],
  );
  return { claim, isPending };
}

export function useAssign() {
  const { mutate, isPending } = useAssignItem();
  const settle = useSettle();
  const assign = useCallback(
    (row: RowRef, assigneeId: number | null, name: string) => {
      mutate(
        { itemId: row.id, data: { assignee_id: assigneeId } },
        {
          onSuccess: () => {
            showToast({
              title:
                assigneeId === null ? `Moved ${row.key} to Unassigned` : `Assigned ${row.key} to ${name}`,
            });
          },
          onError: (error) => {
            showToast({
              tone: 'error',
              title: `Couldn't assign ${row.key}`,
              description: errorMessage(error, 'Nothing was changed. Try again.'),
            });
          },
          onSettled: () => {
            settle(row.id);
          },
        },
      );
    },
    [mutate, settle],
  );
  return { assign, isPending };
}
