import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import type { Viewer } from '../../ui/layout/Viewer';
import { ToastHost } from '../../ui/toast';
import { Board } from './Board';
import { makeRow } from './fixtures';
import { viewSearch } from './search';

const REVIEWER: Viewer = { id: 2, name: 'Dana Whitfield', email: 'dana@x', roles: ['reviewer'] };
const MARKETER: Viewer = { id: 7, name: 'Jordan Ellis', email: 'j@x', roles: ['marketer'] };

const ACTIVE = [
  makeRow({ id: 1, status: 'submitted', assignee: null, title: 'Submitted one' }),
  makeRow({ id: 2, status: 'in_review', title: 'Reviewing one' }),
  makeRow({ id: 3, status: 'changes_requested', title: 'Back with marketer' }),
  makeRow({ id: 4, status: 'needs_rereview', reopen_reason: 'terms_changed', title: 'Terms moved' }),
];
const APPROVED = [makeRow({ id: 5, status: 'approved', title: 'Cleared last week' })];

function serve() {
  const urls: URL[] = [];
  server.use(
    http.get('*/api/items', ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      const approved = url.searchParams.getAll('status').includes('approved');
      return HttpResponse.json({ rows: approved ? APPROVED : ACTIVE, next_cursor: null });
    }),
  );
  return urls;
}

function setup(viewer: Viewer = REVIEWER) {
  const onOpen = vi.fn();
  renderWithQuery(
    <>
      <Board search={viewSearch('active')} viewer={viewer} onOpen={onOpen} />
      <ToastHost />
    </>,
  );
  return { onOpen };
}

describe('Board', () => {
  it('puts each item in its status column', async () => {
    serve();
    setup();
    const column = async (name: string) => within(await screen.findByRole('grid', { name }));
    expect((await column('Submitted')).getByText('Submitted one')).toBeInTheDocument();
    expect((await column('In review')).getByText('Reviewing one')).toBeInTheDocument();
    expect((await column('Changes requested')).getByText('Back with marketer')).toBeInTheDocument();
    expect((await column('Needs re-review')).getByText('Terms moved')).toBeInTheDocument();
    expect((await column('Approved · last 14 days')).getByText('Cleared last week')).toBeInTheDocument();
  });

  it('asks for every board status and only the last 14 days of approvals', async () => {
    const urls = serve();
    setup();
    await screen.findByText('Cleared last week');
    const active = urls.find((u) => !u.searchParams.getAll('status').includes('approved'));
    const approved = urls.find((u) => u.searchParams.getAll('status').includes('approved'));
    expect(active?.searchParams.getAll('status')).toEqual([
      'submitted',
      'in_review',
      'changes_requested',
      'needs_rereview',
    ]);
    expect(approved?.searchParams.get('approved_within_days')).toBe('14');
  });

  it('opens an item from its card', async () => {
    serve();
    const { onOpen } = setup();
    await userEvent.click(await screen.findByText('Reviewing one'));
    expect(onOpen).toHaveBeenCalledWith(2);
  });

  it('claims a submitted item and says so', async () => {
    serve();
    const claimed: string[] = [];
    server.use(
      http.post('*/api/items/:itemId/claim', ({ params }) => {
        claimed.push(String(params.itemId));
        return HttpResponse.json(makeRow({ id: 1, status: 'in_review' }));
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Claim CP-1' }));
    await waitFor(() => {
      expect(claimed).toEqual(['1']);
    });
    expect(await screen.findByText('Claimed CP-1')).toBeInTheDocument();
  });

  it('shows the server message when claiming fails', async () => {
    serve();
    server.use(
      http.post('*/api/items/:itemId/claim', () =>
        HttpResponse.json(
          { code: 'not_implemented', message: 'Claiming is not available yet.' },
          { status: 501 },
        ),
      ),
    );
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Claim CP-1' }));
    expect(await screen.findByText('Claiming is not available yet.')).toBeInTheDocument();
  });

  it('offers no claim to marketers', async () => {
    serve();
    setup(MARKETER);
    await screen.findByText('Submitted one');
    expect(screen.queryByRole('button', { name: /Claim/ })).toBeNull();
  });
});
