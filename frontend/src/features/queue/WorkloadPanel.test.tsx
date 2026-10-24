import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getGetReviewerWorkloadMockHandler } from '../../api/generated/users/users.msw';
import { WORKLOAD } from '../../test/fixtures/users';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { WorkloadPanel } from './WorkloadPanel';

afterEach(() => {
  window.localStorage.clear();
});

function setup() {
  const onPick = vi.fn();
  renderWithQuery(<WorkloadPanel onPick={onPick} />);
  return { onPick };
}

describe('WorkloadPanel', () => {
  it('summarizes when closed, and lists each reviewer heaviest first when opened', async () => {
    server.use(getGetReviewerWorkloadMockHandler(WORKLOAD));
    setup();

    const toggle = await screen.findByRole('button', { name: /Workload by reviewer/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(await screen.findByText(/12 open · heaviest Samuel Ortega, load 13/)).toBeInTheDocument();
    await userEvent.click(toggle);

    const table = screen.getByRole('table', { name: 'Workload by reviewer' });
    const names = within(table)
      .getAllByRole('rowheader')
      .map((c) => c.textContent);
    expect(names[0]).toMatch(/^Samuel Ortega/);
    const leah = within(table).getByRole('row', { name: /Leah Brandt/ });
    expect(within(leah).getByText('Out of office')).toBeInTheDocument();
    const rachel = within(table).getByRole('row', { name: /Rachel Okafor/ });
    expect(within(rachel).getByText('Not auto-assigned')).toBeInTheDocument();
    const sam = within(table).getByRole('row', { name: /Samuel Ortega/ });
    expect(within(sam).getByText('13')).toBeInTheDocument();
  });

  it("opens a reviewer's open items in the queue: the list its count is the total of", async () => {
    server.use(getGetReviewerWorkloadMockHandler(WORKLOAD));
    const { onPick } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /Workload by reviewer/ }));

    await userEvent.click(screen.getByRole('button', { name: '4 open items for Dana Kim' }));

    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({
        view: 'queue',
        status: ['submitted', 'in_review', 'needs_rereview'],
        is_legacy: false,
        assignee_id: [2],
      }),
    );
  });

  it('remembers that it was left open', async () => {
    server.use(getGetReviewerWorkloadMockHandler(WORKLOAD));
    window.localStorage.setItem('clearpath.queue.workload', 'open');
    setup();

    expect(await screen.findByRole('table', { name: 'Workload by reviewer' })).toBeInTheDocument();
  });

  it('says when it could not load, with Retry', async () => {
    window.localStorage.setItem('clearpath.queue.workload', 'open');
    server.use(
      http.get('*/api/users/workload', () =>
        HttpResponse.json({ code: 'server_error', message: 'boom' }, { status: 500 }),
      ),
    );
    setup();

    expect(await screen.findByText("Couldn't load the workload.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
