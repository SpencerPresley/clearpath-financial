import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import type { ItemPageOut, ItemRowOut } from '../../api/generated/model';
import { DECISION_CHANGES, REVIEWER, itemFixture, itemRowFixture } from '../../test/fixtures/review';
import { server } from '../../test/server';
import { MinePage } from './MinePage';
import { renderAtRoute } from './testRouter';

const ROWS: ItemRowOut[] = [
  itemRowFixture({ id: 1, key: 'CP-1', title: 'PL promo — email', status: 'changes_requested' }),
  itemRowFixture({ id: 2, key: 'CP-2', title: 'Card launch', status: 'in_review', assignee: REVIEWER }),
  itemRowFixture({ id: 3, key: 'CP-3', title: 'Spring PL', status: 'approved' }),
  itemRowFixture({ id: 4, key: 'CP-4', title: 'Affiliate page', status: 'withdrawn' }),
];

function listHandler(rows: ItemRowOut[], seen: URLSearchParams[] = []) {
  return http.get('*/api/items', ({ request }) => {
    seen.push(new URL(request.url).searchParams);
    const page: ItemPageOut = { rows, next_cursor: null };
    return HttpResponse.json(page);
  });
}

function detailHandler(fetched: number[] = []) {
  return http.get('*/api/items/:itemId', ({ params }) => {
    const id = Number(params.itemId);
    fetched.push(id);
    return HttpResponse.json(
      itemFixture({
        id,
        key: `CP-${String(id)}`,
        status: 'changes_requested',
        latest_decision: DECISION_CHANGES,
      }),
    );
  });
}

async function renderMine() {
  const rendered = renderAtRoute(MinePage, { path: '/mine' });
  await screen.findByRole('heading', { name: 'My submissions', level: 1 });
  return rendered;
}

describe('MinePage', () => {
  it('asks for my items, most recently updated first', async () => {
    const seen: URLSearchParams[] = [];
    server.use(listHandler([], seen));
    await renderMine();
    await screen.findByText('Nothing submitted yet');
    expect(seen[0]?.get('submitted_by_me')).toBe('true');
    expect(seen[0]?.get('sort')).toBe('updated');
    expect(seen[0]?.get('limit')).toBe('200');
  });

  it('groups items by who they are waiting on, in order, with counts; empty sections are left out', async () => {
    const fetched: number[] = [];
    server.use(listHandler(ROWS), detailHandler(fetched));
    await renderMine();

    const sections = await screen.findAllByRole('region');
    expect(sections.map((section) => section.getAttribute('aria-label'))).toEqual([
      'Waiting on you, 2 items',
      'With compliance, 1 item',
      'Approved, 1 item',
    ]);
    expect(screen.queryByRole('heading', { name: /^Closed/ })).toBeNull();

    const [youSection, complianceSection] = sections;
    if (youSection === undefined || complianceSection === undefined) throw new Error('sections missing');
    const you = within(youSection);
    expect(you.getByRole('link', { name: 'PL promo — email' })).toHaveAttribute('href', '/items/1');
    expect(you.getByRole('link', { name: 'Resubmit CP-1' })).toHaveAttribute('href', '/mine/1/resubmit');
    expect(you.getByRole('link', { name: 'Start new round CP-4' })).toHaveAttribute(
      'href',
      '/mine/4/resubmit',
    );
    expect(
      await you.findByText('Changes requested by Dana Reyes: Add the California license line.'),
    ).toBeInTheDocument();

    const compliance = within(complianceSection);
    expect(compliance.getByText('Dana Reyes is reviewing')).toBeInTheDocument();
    expect(compliance.queryByRole('link', { name: /Resubmit/ })).toBeNull();

    // Details only for the rows whose why line needs the decision.
    expect(fetched).toEqual([1]);
  });

  it('offers a first submission when there is nothing yet', async () => {
    server.use(listHandler([]));
    await renderMine();
    expect(await screen.findByText('Nothing submitted yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'New submission' })).toHaveAttribute('href', '/submit');
  });

  it('says what failed and retries', async () => {
    let calls = 0;
    server.use(
      http.get('*/api/items', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ code: 'internal', message: 'Boom.' }, { status: 500 })
          : HttpResponse.json({ rows: [ROWS[1]], next_cursor: null });
      }),
    );
    const user = userEvent.setup();
    await renderMine();

    expect(await screen.findByText("Couldn't load your submissions.")).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('link', { name: 'Card launch' })).toBeInTheDocument();
  });

  it('shows a skeleton while loading', async () => {
    server.use(
      http.get('*/api/items', async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json({ rows: [], next_cursor: null });
      }),
    );
    await renderMine();
    expect(screen.getByRole('status', { name: 'Loading your submissions' })).toBeInTheDocument();
    await screen.findByText('Nothing submitted yet');
  });
});
