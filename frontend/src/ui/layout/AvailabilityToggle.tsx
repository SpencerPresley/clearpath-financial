/*
 * "Available for new reviews" in the account menu (walkthrough S16). Off means out of office: auto-assignment
 * skips you, and a resubmission of your item goes to someone else (decisions.md, Reviewer assignment). Only for
 * people who do review work (reviewers and leads). Reads the session's own GET /me from the cache, and writes
 * through PATCH /me, which records the change.
 */
import { useQueryClient } from '@tanstack/react-query';

import { getGetMeQueryKey, useGetMe, useUpdateMe } from '../../api/generated/me/me';
import type { MeOut } from '../../api/generated/model';
import { getGetReviewerWorkloadQueryKey, getListUsersQueryKey } from '../../api/generated/users/users';
import { AwayMark } from '../Availability';
import { Switch } from '../Switch';
import { showToast } from '../toast';

export function AvailabilityToggle() {
  const qc = useQueryClient();
  const me = useGetMe();
  const update = useUpdateMe({
    mutation: {
      onSuccess: (next: MeOut) => {
        qc.setQueryData(getGetMeQueryKey(), next);
        void qc.invalidateQueries({ queryKey: getListUsersQueryKey() });
        void qc.invalidateQueries({ queryKey: getGetReviewerWorkloadQueryKey() });
      },
      onError: () => {
        showToast({
          tone: 'error',
          title: 'Couldn’t change your availability',
          description: 'Check your connection and try again.',
        });
      },
    },
  });
  const data = me.data;
  if (data === undefined) return null;
  const reviews = data.effective_roles.includes('reviewer');
  if (!reviews) return null;
  const available = update.isPending
    ? (update.variables.data.is_available ?? data.is_available)
    : data.is_available;
  return (
    <div className="app-availability">
      <Switch
        isSelected={available}
        isDisabled={update.isPending}
        onChange={(is_available) => {
          update.mutate({ data: { is_available } });
        }}
      >
        <span className="app-availability-label">Available for new reviews</span>
      </Switch>
      {!available && <AwayMark />}
    </div>
  );
}
