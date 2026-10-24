/*
 * Below the last row: how much is loaded, the next keyset page, and a failed-page state that keeps the rows
 * already shown (partial state, spec §5.5). Scrolling near the end loads the next page; the button is the
 * keyboard path and the fallback when IntersectionObserver isn't available.
 */
import { useEffect, useRef } from 'react';

import { Button } from '../../ui/Button';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import type { QueueItemsQuery } from './useQueueItems';

function plural(n: number, word: string) {
  return `${String(n)} ${word}${n === 1 ? '' : 's'}`;
}

export function QueueFooter({ query, count }: { query: QueueItemsQuery; count: number }) {
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = query;
  const canAutoLoad = hasNextPage && !isFetchingNextPage && !isFetchNextPageError;

  useEffect(() => {
    const el = sentinel.current;
    if (!canAutoLoad || el === null || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) void fetchNextPage();
      },
      { rootMargin: '240px' },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [canAutoLoad, fetchNextPage]);

  if (isFetchNextPageError) {
    return (
      <div className="app-table-footer" role="alert">
        <Icon name="feedback.error" className="text-status-error-soft-content" />
        <span>{errorMessage(query.error, "Couldn't load more items. Reload the list and try again.")}</span>
        <Button
          size="sm"
          icon="action.reload"
          onPress={() => {
            void query.refetch();
          }}
        >
          Reload
        </Button>
      </div>
    );
  }

  return (
    <div className="app-table-footer">
      <span className="app-figure">
        {hasNextPage ? `${plural(count, 'item')} loaded` : `All ${plural(count, 'item')} loaded`}
      </span>
      {hasNextPage && (
        <Button
          size="sm"
          variant="ghost"
          isDisabled={isFetchingNextPage}
          onPress={() => {
            void fetchNextPage();
          }}
        >
          {isFetchingNextPage ? 'Loading…' : 'Load more'}
        </Button>
      )}
      <div ref={sentinel} aria-hidden="true" />
    </div>
  );
}
