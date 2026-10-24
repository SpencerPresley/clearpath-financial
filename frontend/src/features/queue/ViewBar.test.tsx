import { screen, waitFor } from '@testing-library/react';
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
import { savedViewToSearch, viewSearch } from './search';
import { StatsStrip } from './StatsStrip';
import { ViewBar } from './ViewBar';

describe('ViewBar', () => {
  it('marks the active built-in view and switches views', async () => {
    server.use(getListSavedViewsMockHandler([]));
    const onSelect = vi.fn();
    renderWithQuery(<ViewBar search={viewSearch('mine')} columns={[]} onSelect={onSelect} />);
    expect(screen.getByRole('button', { name: 'My queue' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Unassigned' }));
    expect(onSelect).toHaveBeenCalledWith(viewSearch('unassigned'), undefined);
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
          filters: { mine: true, risk_tier: ['high'] },
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
    renderWithQuery(<ViewBar search={viewSearch('mine')} columns={[]} onSelect={vi.fn()} />);
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
    const mine = await screen.findByRole('button', { name: '8 Mine' });
    expect(screen.getByText('23')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '4 Unassigned' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '6 Waiting >3 days' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2 Re-review' })).toBeInTheDocument();
    await userEvent.click(mine);
    expect(onPick).toHaveBeenCalledWith('mine');
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
