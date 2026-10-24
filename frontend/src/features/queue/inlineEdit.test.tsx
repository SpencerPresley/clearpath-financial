import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import type { ItemRowOut, ItemUpdateIn } from '../../api/generated/model';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { ToastHost } from '../../ui/toast';
import type { Viewer } from '../../ui/layout/Viewer';
import { DEFAULT_COLUMN_VISIBILITY } from './columns';
import { makeRow, USERS } from './fixtures';
import { QueueTable } from './QueueTable';
import { parseQueueSearch } from './search';
import { useQueueCells } from './useItemPatch';
import { useQueueItems } from './useQueueItems';

const REVIEWER: Viewer = { id: 2, name: 'Dana Whitfield', email: 'dana@x', roles: ['reviewer'] };
const LEAD: Viewer = { id: 4, name: 'Priya Raman', email: 'priya@x', roles: ['lead'] };
const MARKETER: Viewer = { id: 7, name: 'Jordan Ellis', email: 'jordan@x', roles: ['marketer'] };

const ROW = makeRow({ id: 1042, risk_tier: 'medium', tags: ['q4-launch'], owner: { id: 7, name: 'Jordan' } });

function Harness({ viewer }: { viewer: Viewer }) {
  const { rows } = useQueueItems(parseQueueSearch({}));
  const cells = useQueueCells(viewer);
  const [active, setActive] = useState<number | null>(1042);
  return (
    <>
      <QueueTable
        rows={rows}
        sort="queue"
        onSortChange={() => undefined}
        activeId={active}
        onActiveChange={setActive}
        onOpen={() => undefined}
        rowSelection={{}}
        onRowSelectionChange={() => undefined}
        columnVisibility={{ ...DEFAULT_COLUMN_VISIBILITY, tags: true }}
        cells={cells}
      />
      <ToastHost />
    </>
  );
}

function serveRow(row: ItemRowOut) {
  let current = row;
  server.use(http.get('*/api/items', () => HttpResponse.json({ rows: [current], next_cursor: null })));
  return {
    set(next: ItemRowOut) {
      current = next;
    },
  };
}

describe('inline edits', () => {
  it('shows a new risk tier before the server answers, then keeps it', async () => {
    const served = serveRow(ROW);
    let release: () => void = () => undefined;
    const bodies: ItemUpdateIn[] = [];
    server.use(
      http.patch('*/api/items/:itemId', async ({ request }) => {
        const body = (await request.json()) as ItemUpdateIn;
        bodies.push(body);
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        const saved = { ...ROW, risk_tier: 'low' as const };
        served.set(saved);
        return HttpResponse.json(saved);
      }),
    );
    renderWithQuery(<Harness viewer={REVIEWER} />);

    await userEvent.click(await screen.findByRole('button', { name: /Risk tier for CP-1042/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'Low risk' }));

    const trigger = () => screen.getByRole('button', { name: /Risk tier for CP-1042/ });
    expect(trigger()).toHaveTextContent('Low');
    await waitFor(() => {
      expect(bodies).toEqual([{ risk_tier: 'low' }]);
    });
    release();
    await waitFor(() => {
      expect(trigger()).toHaveTextContent('Low');
    });
  });

  it('rolls back and toasts the server message on error', async () => {
    serveRow(ROW);
    server.use(
      http.patch('*/api/items/:itemId', () =>
        HttpResponse.json(
          { code: 'not_permitted', message: 'Only reviewers can change risk tier.' },
          { status: 403 },
        ),
      ),
    );
    renderWithQuery(<Harness viewer={REVIEWER} />);

    await userEvent.click(await screen.findByRole('button', { name: /Risk tier for CP-1042/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'High risk' }));

    expect(await screen.findByText('Only reviewers can change risk tier.')).toBeInTheDocument();
    expect(screen.getByText("Couldn't save CP-1042")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Risk tier for CP-1042/ })).toHaveTextContent('Medium');
    });
  });

  it('shows risk as a plain badge to a marketer', async () => {
    serveRow(ROW);
    renderWithQuery(<Harness viewer={MARKETER} />);
    expect(await screen.findByText('Medium')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Risk tier for/ })).toBeNull();
  });

  it('lets the owner add a tag on Enter and remove one with its button', async () => {
    const served = serveRow(ROW);
    const bodies: ItemUpdateIn[] = [];
    server.use(
      http.patch('*/api/items/:itemId', async ({ request }) => {
        const body = (await request.json()) as ItemUpdateIn;
        bodies.push(body);
        const saved = { ...ROW, tags: body.tags ?? ROW.tags };
        served.set(saved);
        return HttpResponse.json(saved);
      }),
    );
    renderWithQuery(<Harness viewer={MARKETER} />);

    await userEvent.click(await screen.findByRole('button', { name: /Tags for CP-1042/ }));
    const input = await screen.findByRole('textbox', { name: 'Add tag' });
    await userEvent.type(input, 'affiliate {Enter}');
    await waitFor(() => {
      expect(bodies.at(-1)).toEqual({ tags: ['q4-launch', 'affiliate'] });
    });

    await userEvent.click(screen.getByRole('button', { name: 'Remove tag q4-launch' }));
    await waitFor(() => {
      expect(bodies.at(-1)).toEqual({ tags: ['affiliate'] });
    });
  });

  it('refuses a tag longer than 50 characters without calling the server', async () => {
    serveRow(ROW);
    let calls = 0;
    server.use(
      http.patch('*/api/items/:itemId', () => {
        calls += 1;
        return HttpResponse.json(ROW);
      }),
    );
    renderWithQuery(<Harness viewer={MARKETER} />);
    await userEvent.click(await screen.findByRole('button', { name: /Tags for CP-1042/ }));
    await userEvent.type(await screen.findByRole('textbox', { name: 'Add tag' }), `${'x'.repeat(51)}{Enter}`);
    expect(await screen.findByText('Tags are 50 characters or fewer.')).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it('lets a reviewer claim an unassigned submitted item from the table', async () => {
    serveRow(makeRow({ id: 1044, status: 'submitted', assignee: null }));
    let claimed: string | undefined;
    server.use(
      http.post('*/api/items/:id/claim', ({ params }) => {
        claimed = String(params.id);
        return HttpResponse.json(makeRow({ id: 1044, status: 'in_review' }));
      }),
    );
    renderWithQuery(<Harness viewer={REVIEWER} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Claim CP-1044' }));
    await waitFor(() => {
      expect(claimed).toBe('1044');
    });
    expect(await screen.findByText('Claimed CP-1044')).toBeInTheDocument();
  });

  it("offers a reviewer neither claim nor reassign on someone else's item", async () => {
    serveRow(makeRow({ id: 1044, status: 'in_review', assignee: { id: 3, name: 'Sam Okafor' } }));
    renderWithQuery(<Harness viewer={REVIEWER} />);
    expect(await screen.findByText('Sam Okafor')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Claim CP-1044|Assignee for CP-1044/ })).toBeNull();
  });

  it('lets a lead reassign from the assignee cell', async () => {
    serveRow(makeRow({ id: 1044, assignee: { id: 2, name: 'Dana Whitfield' } }));
    let body: unknown;
    server.use(
      getListUsersMockHandler(USERS),
      http.post('*/api/items/:id/assign', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeRow({ id: 1044, assignee: { id: 3, name: 'Sam Okafor' } }));
      }),
    );
    renderWithQuery(<Harness viewer={LEAD} />);
    await userEvent.click(await screen.findByRole('button', { name: /^Assignee for CP-1044/ }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sam Okafor' }));
    await waitFor(() => {
      expect(body).toEqual({ assignee_id: 3 });
    });
    expect(await screen.findByText('Assigned CP-1044 to Sam Okafor')).toBeInTheDocument();
  });
});
