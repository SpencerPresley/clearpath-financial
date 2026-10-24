/*
 * Keyset pages for the partner's items (GET /items) and findings history (GET /partners/{id}/findings). The
 * generated hooks are single-page queries, so these compose the generated fetchers and keys with
 * useInfiniteQuery. A 'pages' suffix keeps them apart from single-page entries for the same params, while
 * the path prefix still matches them for invalidation.
 */
import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { getListItemsQueryKey, listItems } from '../../api/generated/items/items';
import type { ItemRowOut, ListItemsParams, PartnerFindingOut } from '../../api/generated/model';
import { getListPartnerFindingsQueryKey, listPartnerFindings } from '../../api/generated/partners/partners';

export const PAGE_SIZE = 50;

const NO_ITEMS: ItemRowOut[] = [];
const NO_FINDINGS: PartnerFindingOut[] = [];

/** Every item for the partner, any status (legacy imports included), newest first. */
export function partnerItemsParams(partnerId: number): ListItemsParams {
  return { partner_id: [partnerId], sort: 'newest', limit: PAGE_SIZE };
}

export function usePartnerItems(partnerId: number) {
  const params = partnerItemsParams(partnerId);
  const query = useInfiniteQuery({
    queryKey: [...getListItemsQueryKey(params), 'pages'],
    queryFn: ({ pageParam, signal }) =>
      listItems(pageParam === null ? params : { ...params, cursor: pageParam }, { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.rows) ?? NO_ITEMS, [query.data]);
  return { query, rows };
}

/** The partner's findings history, newest first; `ruleId` narrows it to one rule. */
export function usePartnerFindings(partnerId: number, ruleId?: string) {
  const params = ruleId === undefined ? { limit: PAGE_SIZE } : { limit: PAGE_SIZE, rule_id: ruleId };
  const query = useInfiniteQuery({
    queryKey: [...getListPartnerFindingsQueryKey(partnerId, params), 'pages'],
    queryFn: ({ pageParam, signal }) =>
      listPartnerFindings(partnerId, pageParam === null ? params : { ...params, cursor: pageParam }, {
        signal,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.rows) ?? NO_FINDINGS, [query.data]);
  return { query, rows };
}
