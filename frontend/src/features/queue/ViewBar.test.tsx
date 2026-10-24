import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import {
  getCreateSavedViewMockHandler,
  getGetQueueStatsMockHandler,
  getListSavedViewsMockHandler,
} from '../../api/generated/items/items.msw';
import type { SavedViewIn } from '../../api/generated/model';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { AFFILIATE_VIEW, STATS } from './fixtures';
import { savedViewToSearch, statSearch, viewSearch } from './search';
import { StatsStrip } from './StatsStrip';
import { SavedViewsError, ViewBar } from './ViewBar';

describe('ViewBar', () => {
  it('marks the active built-in view and switches views', async () => {
    server.use(getListSavedViewsMockHandler([]));
    const onSelect = vi.fn();
    renderWithQuery(<ViewBar search={viewSearch('mine')} columns={[]} onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: 'My queue' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Unassigned' }));
    expect(onSelect).toHaveBeenCalledWith(viewSearch('unassigned'), undefined);
  });

  it('has no tab for In queue (its stat opens it) and keeps five tabs', () => {
    server.use(getListSavedViewsMockHandler([]));
    renderWithQuery(<ViewBar search={viewSearch('queue')} columns={[]} onSelect={vi.fn()} />);
    const tabs = within(screen.getByRole('group', { name: 'Views' })).getAllByRole('button');
    expect(tabs.map((t) => t.textContent)).toEqual([
      'My queue',
      'Unassigned',
      'Waiting >3 days',
      'Needs re-review',
      'All active',
    ]);
    expect(screen.queryByText('Modified')).toBeNull();
  });

  it('says Modified when filters move off the view', () => {
    server.use(getListSavedViewsMockHandler([]));
    renderWithQuery(
      <ViewBar search={{ ...viewSearch('mine'), risk_tier: ['high'] }} columns={[]} onSelect={vi.fn()} />,
    );
    expect(screen.getByText('Modified')).toBeInTheDocument();
  });

  it('lists saved views and opens one with its columns', async () => {
    server.use(getListSavedViewsMockHandler([{ ...AFFILIATE_VIEW, columns: ['key', 'title'] }]));
    const onSelect = vi.fn();
    renderWithQuery(<ViewBar search={viewSearch('mine')} columns={[]} onSelect={onSelect} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Affiliate, high risk' }));
    expect(onSelect).toHaveBeenCalledWith(savedViewToSearch(AFFILIATE_VIEW), ['key', 'title']);
  });

  it('saves the current filters, sort, and columns as a new view', async () => {
    const bodies: SavedViewIn[] = [];
    server.use(
      getListSavedViewsMockHandler([]),
      getCreateSavedViewMockHandler(async ({ request }) => {
        const body = (await request.json()) as SavedViewIn;
        bodies.push(body);
        return { ...body, id: 31, created_at: '2026-10-24T10:00:00Z', columns: body.columns ?? [] };
      }),
    );
    const onSelect = vi.fn();
    const search = { ...viewSearch('mine'), risk_tier: ['high' as const], sort: 'oldest' as const };
    renderWithQuery(<ViewBar search={search} columns={['key', 'title', 'status']} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Save view' }));
    await userEvent.type(await screen.findByRole('textbox', { name: 'View name' }), 'Mine, high risk');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(bodies).toEqual([
        {
          name: 'Mine, high risk',
          // The view's own definition travels with it, so the saved view is the same set under any sort.
          filters: {
            status: ['submitted', 'in_review', 'needs_rereview'],
            is_legacy: false,
            mine: true,
            risk_tier: ['high'],
          },
          sort: 'oldest',
          columns: ['key', 'title', 'status'],
        },
      ]);
    });
    await waitFor(() => {
      expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ view: 'saved:31' }), [
        'key',
        'title',
        'status',
      ]);
    });
  });

  it('keeps built-in views usable when saved views fail to load', async () => {
    server.use(
      http.get('*/api/views', () => HttpResponse.json({ code: 'x', message: 'boom' }, { status: 500 })),
    );
    renderWithQuery(
      <>
        <ViewBar search={viewSearch('mine')} columns={[]} onSelect={vi.fn()} />
        <SavedViewsError />
      </>,
    );
    expect(await screen.findByText("Couldn't load saved views.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unassigned' })).toBeEnabled();
  });
});

describe('StatsStrip', () => {
  it('shows real counts and applies a view from a figure', async () => {
    server.use(getGetQueueStatsMockHandler(STATS));
    const onPick = vi.fn();
    renderWithQuery(<StatsStrip onPick={onPick} />);
    const mine = await screen.findByRole('button', { name: '8 My queue' });
    expect(screen.getByRole('button', { name: '4 Unassigned' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '6 Waiting >3 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2 Needs re-review' })).toBeInTheDocument();
    await userEvent.click(mine);
    // The view, with the filters the server counted it with: the list's total is the number clicked.
    expect(onPick).toHaveBeenLastCalledWith(statSearch('mine', STATS.filters.mine));
    expect(onPick.mock.lastCall?.[0]).toMatchObject({ view: 'mine', is_legacy: false, mine: true });
  });

  it('links In queue to its own view too', async () => {
    server.use(getGetQueueStatsMockHandler(STATS));
    const onPick = vi.fn();
    renderWithQuery(<StatsStrip onPick={onPick} active="queue" />);
    const open = await screen.findByRole('button', { name: '23 In queue' });
    expect(open).toHaveAttribute('data-active', 'true');
    await userEvent.click(open);
    expect(onPick).toHaveBeenLastCalledWith(statSearch('open', STATS.filters.open));
  });

  it('says stats are unavailable without hiding anything else', async () => {
    server.use(
      http.get('*/api/items/stats', () => HttpResponse.json({ code: 'x', message: 'down' }, { status: 500 })),
    );
    renderWithQuery(<StatsStrip onPick={vi.fn()} />);
    expect(await screen.findByText("Couldn't load queue counts.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
