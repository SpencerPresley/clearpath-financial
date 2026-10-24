import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { getListFindingsQueryKey, useListFindings } from '../../api/generated/findings/findings';
import {
  getGetItemHistoryQueryKey,
  useGetItem,
  useGetVersion,
  useListItemAttachments,
} from '../../api/generated/items/items';
import type { CheckStatus, ItemDetailOut } from '../../api/generated/model';

/** While the AI check is queued or running, the item is polled so its findings arrive without a reload. */
export const LLM_POLL_MS = 3000;

const IN_FLIGHT: readonly CheckStatus[] = ['pending', 'running'];

export function isLlmInFlight(item: Pick<ItemDetailOut, 'llm_check_status'> | undefined): boolean {
  return item !== undefined && IN_FLIGHT.includes(item.llm_check_status);
}

/**
 * Everything the review screen reads for one item and the version on screen. `requestedN` is the `v`
 * search param; undefined means the current version.
 */
export function useReviewData(itemId: number, requestedN: number | undefined) {
  const queryClient = useQueryClient();
  const item = useGetItem(itemId, {
    query: { refetchInterval: (query) => (isLlmInFlight(query.state.data) ? LLM_POLL_MS : false) },
  });

  const currentN = item.data?.current_version_n ?? null;
  const shownN = requestedN ?? currentN;
  const viewingCurrent = shownN === currentN;

  const findings = useListFindings(itemId, shownN === null ? undefined : { version_n: shownN }, {
    query: { enabled: shownN !== null },
  });
  const olderVersion = useGetVersion(itemId, shownN ?? 0, {
    query: { enabled: shownN !== null && !viewingCurrent },
  });
  const attachments = useListItemAttachments(itemId);

  // When the AI check finishes (or fails), its findings and events are new: refetch them once.
  const llmStatus = item.data?.llm_check_status;
  const previous = useRef(llmStatus);
  useEffect(() => {
    const was = previous.current;
    previous.current = llmStatus;
    if (was !== undefined && llmStatus !== undefined && was !== llmStatus && IN_FLIGHT.includes(was)) {
      void queryClient.invalidateQueries({ queryKey: getListFindingsQueryKey(itemId) });
      void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(itemId) });
    }
  }, [llmStatus, itemId, queryClient]);

  const version = viewingCurrent ? (item.data?.current_version ?? undefined) : olderVersion.data;

  return {
    item,
    findings,
    attachments,
    version,
    versionLoading: !viewingCurrent && olderVersion.isPending,
    shownN,
    currentN,
    viewingCurrent,
  };
}
