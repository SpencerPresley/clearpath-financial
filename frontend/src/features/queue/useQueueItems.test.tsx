import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { makeRow } from './fixtures';
import { QueueFooter } from './QueueFooter';
import { parseQueueSearch } from './search';
import { useQueueItems } from './useQueueItems';

function List() {
  const { rows, query } = useQueueItems(parseQueueSearch({}));
  return (
    <div>
      <ul>
        {rows.map((r) => (
          <li key={r.id}>{r.key}</li>
        ))}
      </ul>
      <QueueFooter query={query} count={rows.length} />
    </div>
  );
}

describe('useQueueItems', () => {
  it('loads keyset pages and appends them in order', async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get('*/api/items', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        seen.push(cursor);
        return cursor === null
          ? HttpResponse.json({ rows: [makeRow({ id: 1 }), makeRow({ id: 2 })], next_cursor: 'c2', total: 3 })
          : HttpResponse.json({ rows: [makeRow({ id: 3 })], next_cursor: null, total: 3 });
      }),
    );
    renderWithQuery(<List />);
    expect(await screen.findByText('CP-2')).toBeInTheDocument();
    expect(screen.getByText('2 of 3 items loaded')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Load more' }));
    expect(await screen.findByText('CP-3')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['CP-1', 'CP-2', 'CP-3']);
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
    expect(screen.getByText('All 3 items loaded')).toBeInTheDocument();
    expect(seen).toEqual([null, 'c2']);
  });

  it('sends the queue filters with every page', async () => {
    const urls: URL[] = [];
    server.use(
      http.get('*/api/items', ({ request }) => {
        urls.push(new URL(request.url));
        return HttpResponse.json({ rows: [], next_cursor: null, total: 0 });
      }),
    );
    renderWithQuery(<List />);
    expect(await screen.findByText('All 0 items loaded')).toBeInTheDocument();
    expect(urls[0]?.searchParams.get('mine')).toBe('true');
    expect(urls[0]?.searchParams.get('sort')).toBe('queue');
  });

  it('shows the server message with Reload when a later page fails', async () => {
    let failNext = true;
    server.use(
      http.get('*/api/items', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        if (cursor === null) {
          return HttpResponse.json({ rows: [makeRow({ id: 1 })], next_cursor: 'stale', total: 2 });
        }
        if (failNext) {
          failNext = false;
          return HttpResponse.json(
            { code: 'invalid_input', message: 'This page link is out of date. Reload the list.' },
            { status: 422 },
          );
        }
        return HttpResponse.json({ rows: [makeRow({ id: 2 })], next_cursor: null, total: 2 });
      }),
    );
    renderWithQuery(<List />);
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }));
    expect(await screen.findByText('This page link is out of date. Reload the list.')).toBeInTheDocument();
    expect(screen.getByText('CP-1')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(await screen.findByRole('button', { name: 'Load more' })).toBeInTheDocument();
    expect(screen.queryByText(/out of date/)).toBeNull();
  });
});
