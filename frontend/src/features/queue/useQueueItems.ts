/*
 * The queue list: keyset pages from GET /items, appended. The generated useListItems is a single-page query,
 * so this composes the generated listItems + getListItemsQueryKey with useInfiniteQuery. The key gets a
 * 'pages' suffix so an infinite cache entry never collides with a plain useListItems entry for the same
 * params (the board uses those), while ['/api/items'] still prefix-matches both for invalidation.
 */
import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query';
import type { InfiniteData, QueryKey } from '@tanstack/react-query';
import { useMemo } from 'react';

import { getListItemsQueryKey, listItems } from '../../api/generated/items/items';
import type { ItemPageOut, ItemRowOut, ListItemsParams } from '../../api/generated/model';
import { toListParams } from './search';
import type { QueueSearch } from './search';

export const PAGE_SIZE = 50;

const EMPTY_ROWS: ItemRowOut[] = [];

export function queueItemsKey(params: ListItemsParams): QueryKey {
  return [...getListItemsQueryKey(params), 'pages'];
}

export type QueuePages = InfiniteData<ItemPageOut, string | null>;

export function useQueueItems(search: QueueSearch, options: { enabled?: boolean } = {}) {
  const params = toListParams(search, { limit: PAGE_SIZE });
  const query = useInfiniteQuery({
    queryKey: queueItemsKey(params),
    queryFn: ({ pageParam, signal }) =>
      listItems(pageParam === null ? params : { ...params, cursor: pageParam }, { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    // Keep the old rows on screen while a filter change loads (marked busy), instead of flashing a skeleton.
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.rows) ?? EMPTY_ROWS, [query.data]);
  return { rows, query, queryKey: queueItemsKey(params) };
}

export type QueueItemsQuery = ReturnType<typeof useQueueItems>['query'];
