import { useQueryClient } from '@tanstack/react-query';

import {
  getListFindingsQueryKey,
  useAcceptFinding,
  useDismissFinding,
  useReopenFinding,
} from '../../api/generated/findings/findings';
import { getGetItemHistoryQueryKey, getGetItemQueryKey } from '../../api/generated/items/items';
import type { FindingOut } from '../../api/generated/model';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { showToast } from '../../ui/toast';

/**
 * Accept / dismiss / reopen. Each response is the finding's new state, written straight into the
 * findings cache (no refetch flash); the item (open count) and history are refetched behind it.
 */
export function useTriage(itemId: number, versionN: number | null) {
  const queryClient = useQueryClient();
  const findingsKey = getListFindingsQueryKey(
    itemId,
    versionN === null ? undefined : { version_n: versionN },
  );

  const onSuccess = (updated: FindingOut) => {
    queryClient.setQueryData<FindingOut[]>(findingsKey, (old) =>
      old?.map((finding) => (finding.id === updated.id ? updated : finding)),
    );
    void queryClient.invalidateQueries({ queryKey: getGetItemQueryKey(itemId) });
    void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(itemId) });
  };
  const onError = (title: string) => (error: unknown) => {
    showToast({ title, description: apiErrorMessage(error), tone: 'error' });
  };

  const accept = useAcceptFinding({ mutation: { onSuccess, onError: onError('Finding not accepted') } });
  const dismiss = useDismissFinding({ mutation: { onSuccess, onError: onError('Finding not dismissed') } });
  const reopen = useReopenFinding({ mutation: { onSuccess, onError: onError('Finding not reopened') } });

  return {
    accept: (findingId: number) => {
      accept.mutate({ findingId, data: {} });
    },
    /** `onDone` runs only on success (the reason form closes then; on failure it stays with its text). */
    dismiss: (findingId: number, reason: string, onDone?: () => void) => {
      dismiss.mutate({ findingId, data: { reason } }, { onSuccess: onDone });
    },
    reopen: (findingId: number) => {
      reopen.mutate({ findingId });
    },
    pendingId:
      (accept.isPending ? accept.variables.findingId : undefined) ??
      (dismiss.isPending ? dismiss.variables.findingId : undefined) ??
      (reopen.isPending ? reopen.variables.findingId : undefined),
  };
}
