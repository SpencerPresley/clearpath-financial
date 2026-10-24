import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { getListFindingsMockHandler } from '../../api/generated/findings/findings.msw';
import { getGetItemMockHandler } from '../../api/generated/items/items.msw';
import type { ItemUpdateIn } from '../../api/generated/model';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import type { Viewer } from '../../ui/layout/Viewer';
import { FINDINGS, makeDecision, makeDetail, makeRow } from './fixtures';
import { PreviewDrawer } from './PreviewDrawer';

const REVIEWER: Viewer = { id: 2, name: 'Dana Whitfield', email: 'dana@x', roles: ['reviewer'] };
const MARKETER: Viewer = { id: 99, name: 'Someone', email: 's@x', roles: ['marketer'] };

const DETAIL = makeDetail(
  makeRow({
    id: 1047,
    title: 'RateRadar lead-gen form copy',
    status: 'in_review',
    risk_tier: 'high',
    channel: 'affiliate_page',
    partner: { id: 13, name: 'RateRadar' },
    round: 3,
    current_version_n: 3,
    open_findings_count: 3,
  }),
  {
    latest_decision: makeDecision({ outcome: 'changes_requested', version_n: 2 }),
    notes: 'Partner asked for a rush; launch is 11/1.',
  },
);

function setup(viewer: Viewer = REVIEWER) {
  server.use(getGetItemMockHandler(DETAIL), getListFindingsMockHandler(FINDINGS));
  const onClose = vi.fn();
  const onOpenReview = vi.fn();
  renderWithQuery(
    <PreviewDrawer itemId={1047} viewer={viewer} onClose={onClose} onOpenReview={onOpenReview} />,
  );
  return { onClose, onOpenReview };
}

describe('PreviewDrawer', () => {
  it('summarises the item', async () => {
    setup();
    const drawer = await screen.findByRole('complementary', { name: 'Preview CP-1047' });
    const d = within(drawer);
    expect(await d.findByRole('heading', { name: 'RateRadar lead-gen form copy' })).toBeInTheDocument();
    expect(d.getByText('In review')).toBeInTheDocument();
    expect(d.getByText('RateRadar')).toBeInTheDocument();
    expect(d.getByText('Affiliate page')).toBeInTheDocument();
    expect(d.getByText('R3 · v3')).toBeInTheDocument();
    expect(d.getByText('High risk')).toBeInTheDocument();
  });

  it('counts open findings by severity, ignoring triaged ones', async () => {
    setup();
    expect(await screen.findByText('2 blocking')).toBeInTheDocument();
    expect(screen.getByText('1 warning')).toBeInTheDocument();
  });

  it('shows the latest decision with who and why', async () => {
    setup();
    expect(await screen.findByText('Changes requested')).toBeInTheDocument();
    expect(screen.getByText(/Dana Whitfield · v2/)).toBeInTheDocument();
    expect(screen.getByText('Add the APR range next to the rate claim.')).toBeInTheDocument();
  });

  it('opens the review and closes on Escape', async () => {
    const { onClose, onOpenReview } = setup();
    await userEvent.click(await screen.findByRole('link', { name: /Open review/ }));
    expect(onOpenReview).toHaveBeenCalledWith(1047);

    screen.getByRole('heading', { name: 'RateRadar lead-gen form copy' }).focus();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('saves notes on blur for a reviewer', async () => {
    const bodies: ItemUpdateIn[] = [];
    setup();
    server.use(
      http.patch('*/api/items/:itemId', async ({ request }) => {
        bodies.push((await request.json()) as ItemUpdateIn);
        return HttpResponse.json(makeRow({ id: 1047 }));
      }),
    );
    const notes = await screen.findByRole('textbox', { name: 'Notes' });
    await userEvent.clear(notes);
    await userEvent.type(notes, 'Rush: launch 11/1');
    await userEvent.tab();
    await waitFor(() => {
      expect(bodies).toEqual([{ notes: 'Rush: launch 11/1' }]);
    });
  });

  it('shows notes read-only to someone who cannot edit them', async () => {
    setup(MARKETER);
    expect(await screen.findByText('Partner asked for a rush; launch is 11/1.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Notes' })).toBeNull();
  });

  it('says when the item no longer exists', async () => {
    server.use(
      http.get('*/api/items/:itemId', () =>
        HttpResponse.json({ code: 'not_found', message: 'Item 1047 not found.' }, { status: 404 }),
      ),
      getListFindingsMockHandler([]),
    );
    renderWithQuery(
      <PreviewDrawer itemId={1047} viewer={REVIEWER} onClose={vi.fn()} onOpenReview={vi.fn()} />,
    );
    expect(await screen.findByText('CP-1047 no longer exists.')).toBeInTheDocument();
  });
});
