/*
 * The inbox's data: one polled list (the bell's count is its unread_count), and read receipts applied to that
 * cache optimistically (spec §5.7: low-stakes). No websockets: a 30 s poll, plus TanStack Query's refetch on
 * window focus (queryClient.ts); polling pauses while the tab is hidden.
 */
import { useQueryClient } from '@tanstack/react-query';

import {
  getListNotificationsQueryKey,
  useListNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
} from '../../api/generated/notifications/notifications';
import type { NotificationPageOut } from '../../api/generated/model';
import { showToast } from '../../ui/toast';

export const POLL_MS = 30_000;

export function useNotifications() {
  return useListNotifications(undefined, { query: { refetchInterval: POLL_MS } });
}

interface Snapshot {
  previous: NotificationPageOut | undefined;
}

function useOptimisticRead() {
  const queryClient = useQueryClient();
  const key = getListNotificationsQueryKey();

  const apply = async (read: (id: number) => boolean): Promise<Snapshot> => {
    await queryClient.cancelQueries({ queryKey: key });
    const previous = queryClient.getQueryData<NotificationPageOut>(key);
    if (previous !== undefined) {
      const at = new Date().toISOString();
      let marked = 0;
      const rows = previous.rows.map((row) => {
        if (row.read_at !== null || !read(row.id)) return row;
        marked += 1;
        return { ...row, read_at: at };
      });
      queryClient.setQueryData<NotificationPageOut>(key, {
        rows,
        unread_count: Math.max(0, previous.unread_count - marked),
      });
    }
    return { previous };
  };

  const rollback = (context: Snapshot | undefined) => {
    if (context?.previous !== undefined) queryClient.setQueryData(key, context.previous);
  };

  const settle = () => queryClient.invalidateQueries({ queryKey: key });

  return { apply, rollback, settle };
}

/** Mark one read. Lives in the always-mounted bell, so a row's click survives the popover closing. */
export function useMarkRead() {
  const { apply, rollback, settle } = useOptimisticRead();
  return useMarkNotificationRead<unknown, Snapshot>({
    mutation: {
      onMutate: ({ notificationId }) => apply((id) => id === notificationId),
      onError: (_error, _vars, context) => {
        rollback(context);
      },
      onSettled: settle,
    },
  });
}

export function useMarkAllRead() {
  const { apply, rollback, settle } = useOptimisticRead();
  return useMarkAllNotificationsRead<unknown, Snapshot>({
    mutation: {
      onMutate: () => apply(() => true),
      onError: (_error, _vars, context) => {
        rollback(context);
        showToast({
          tone: 'error',
          title: 'Couldn’t mark notifications read',
          description: 'Check your connection and try again.',
        });
      },
      onSettled: settle,
    },
  });
}
