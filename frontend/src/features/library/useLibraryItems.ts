/*
 * The approved list: keyset pages from GET /library, appended. Composes the generated listLibrary and its query
 * key with useInfiniteQuery (the generated hook is single-page); the 'pages' suffix keeps it apart from a plain
 * useListLibrary entry while ['/api/library'] still prefix-matches both.
 */
import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { getListLibraryQueryKey, listLibrary } from '../../api/generated/library/library';
import type { ItemRowOut } from '../../api/generated/model';
import { toListParams } from './search';
import type { LibrarySearch } from './search';

const EMPTY: ItemRowOut[] = [];

export function useLibraryItems(search: LibrarySearch, enabled: boolean) {
  const params = toListParams(search);
  const query = useInfiniteQuery({
    queryKey: [...getListLibraryQueryKey(params), 'pages'],
    queryFn: ({ pageParam, signal }) => listLibrary(toListParams(search, pageParam), { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    enabled,
  });
  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.rows) ?? EMPTY, [query.data]);
  return { rows, query };
}

export type LibraryItemsQuery = ReturnType<typeof useLibraryItems>['query'];
