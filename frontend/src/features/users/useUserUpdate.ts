/*
 * One PATCH /admin/users/{id} per change. On success the row is replaced in the cached list (no refetch flash) and
 * every other user list (assignee pickers, @mentions), the workload and the queue are refreshed (deactivating a
 * reviewer reassigns their open items). A refusal (409: the last
 * admin, deactivating yourself) is kept as the page's one error line; the row keeps the server's state.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { useUpdateUser } from '../../api/generated/admin/admin';
import { getGetQueueStatsQueryKey, getListItemsQueryKey } from '../../api/generated/items/items';
import type { UserOut, UserUpdateIn } from '../../api/generated/model';
import { getGetReviewerWorkloadQueryKey, getListUsersQueryKey } from '../../api/generated/users/users';
import { apiErrorMessage } from '../../ui/forms/apiErrors';

export const USERS_PARAMS = { include_inactive: true } as const;

export function useUserUpdate() {
  const qc = useQueryClient();
  const [error, setError] = useState<{ userId: number; message: string } | null>(null);
  const mutation = useUpdateUser({
    mutation: {
      onMutate: () => {
        setError(null);
      },
      onSuccess: (user: UserOut) => {
        qc.setQueryData<UserOut[]>(getListUsersQueryKey(USERS_PARAMS), (rows) =>
          rows?.map((r) => (r.id === user.id ? user : r)),
        );
        void qc.invalidateQueries({
          predicate: (q) =>
            q.queryKey[0] === getListUsersQueryKey()[0] &&
            JSON.stringify(q.queryKey) !== JSON.stringify(getListUsersQueryKey(USERS_PARAMS)),
        });
        void qc.invalidateQueries({ queryKey: getGetReviewerWorkloadQueryKey() });
        void qc.invalidateQueries({ queryKey: getListItemsQueryKey().slice(0, 1) });
        void qc.invalidateQueries({ queryKey: getGetQueueStatsQueryKey() });
      },
      onError: (err, { userId }) => {
        setError({ userId, message: apiErrorMessage(err) });
      },
    },
  });
  return {
    error,
    pendingId: mutation.isPending ? mutation.variables.userId : null,
    update: (userId: number, data: UserUpdateIn) => {
      mutation.mutate({ userId, data });
    },
  };
}
