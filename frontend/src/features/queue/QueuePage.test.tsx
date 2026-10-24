import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getListFindingsMockHandler } from '../../api/generated/findings/findings.msw';
import {
  getGetItemMockHandler,
  getGetQueueStatsMockHandler,
  getListSavedViewsMockHandler,
} from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import type { ItemRowOut } from '../../api/generated/model';
import { renderApp, searchString } from '../../test/renderApp';
import { server } from '../../test/server';
import { FINDINGS, makeDetail, ME_REVIEWER, PARTNERS, queueRows, STATS, USERS } from './fixtures';

function serveItems(rows: ItemRowOut[]) {
  server.use(http.get('*/api/items', () => HttpResponse.json({ rows, next_cursor: null })));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    getGetMeMockHandler(ME_REVIEWER),
    getGetQueueStatsMockHandler(STATS),
    getListSavedViewsMockHandler([]),
    getListUsersMockHandler(USERS),
    getListPartnersMockHandler(PARTNERS),
    getListFindingsMockHandler(FINDINGS),
  );
});

describe('QueuePage', () => {
  it('opens to My queue and says why it is empty, with the next action', async () => {
    serveItems([]);
    const { router } = renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Nothing assigned to you' })).toBeInTheDocument();
    expect(await screen.findByText('4 unassigned items')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'My queue' })).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(screen.getByRole('button', { name: 'Show unassigned' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ view: 'unassigned', unassigned: true });
    });
  });

  it('says no items match when filters narrow a view to nothing', async () => {
    serveItems([]);
    renderApp(`/${searchString({ view: 'mine', mine: true, risk_tier: ['high'] })}`);
    expect(await screen.findByRole('heading', { name: 'No items match these filters' })).toBeInTheDocument();
    expect(screen.getByText('Modified')).toBeInTheDocument();
  });

  it('shows the load error with retry while the counts still render', async () => {
    server.use(
      http.get('*/api/items', () =>
        HttpResponse.json(
          { code: 'server_error', message: 'The queue is temporarily unavailable.' },
          { status: 503 },
        ),
      ),
    );
    renderApp('/');
    expect(await screen.findByRole('heading', { name: "Couldn't load the queue" })).toBeInTheDocument();
    expect(screen.getByText('The queue is temporarily unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '8 Mine' })).toBeInTheDocument();
  });

  it('drives the list from the keyboard: j/k, x, Enter, Escape, o', async () => {
    const rows = queueRows();
    serveItems(rows);
    const [first, second] = rows;
    if (first === undefined || second === undefined) throw new Error('fixture needs two rows');
    server.use(getGetItemMockHandler(makeDetail(second)));
    const { router } = renderApp('/');
    await screen.findByText(first.title);

    await userEvent.keyboard('j');
    expect(document.activeElement).toHaveTextContent(first.key);
    await userEvent.keyboard('j');
    expect(document.activeElement).toHaveTextContent(second.key);
    await userEvent.keyboard('k');
    expect(document.activeElement).toHaveTextContent(first.key);
    await userEvent.keyboard('j');

    await userEvent.keyboard('x');
    expect(await screen.findByText('1 selected')).toBeInTheDocument();
    await userEvent.keyboard('x');
    expect(screen.queryByText('1 selected')).toBeNull();

    await userEvent.keyboard('{Enter}');
    const drawer = await screen.findByRole('complementary', { name: `Preview ${second.key}` });
    expect(await within(drawer).findByRole('heading', { name: second.title })).toBeInTheDocument();
    expect(router.state.location.search).toMatchObject({ item: second.id });

    await userEvent.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('complementary', { name: /Preview/ })).toBeNull();
    });

    await userEvent.keyboard('o');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/items/${String(second.id)}`);
    });
  });

  it('opens the shortcuts help with ?', async () => {
    serveItems(queueRows());
    renderApp('/');
    await screen.findByText('RateRadar lead-gen form copy');
    await act(async () => {
      await userEvent.keyboard('?');
    });
    expect(await screen.findByRole('dialog', { name: 'Keyboard shortcuts' })).toBeInTheDocument();
  });

  it('switches to the board and keeps the filters in the URL', async () => {
    serveItems(queueRows());
    const { router } = renderApp('/');
    await screen.findByText('RateRadar lead-gen form copy');
    await userEvent.click(screen.getByRole('radio', { name: 'Board' }));
    expect(await screen.findByRole('grid', { name: 'Submitted' })).toBeInTheDocument();
    expect(router.state.location.search).toMatchObject({ layout: 'board', mine: true });
    expect(screen.queryByRole('button', { name: 'Status' })).toBeNull();
  });
});
