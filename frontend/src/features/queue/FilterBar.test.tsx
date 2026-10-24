import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ItemSort } from '../../api/generated/model';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import { getListUsersMockHandler } from '../../api/generated/users/users.msw';
import { server } from '../../test/server';
import { renderWithQuery } from '../../test/render';
import { FilterBar, SortMenu } from './FilterBar';
import { PARTNERS, USERS } from './fixtures';
import { parseQueueSearch, viewSearch } from './search';
import type { QueueSearch } from './search';

function Harness({ initial, spy }: { initial: QueueSearch; spy: (s: QueueSearch) => void }) {
  const [search, setSearch] = useState(initial);
  return (
    <FilterBar
      search={search}
      onChange={(patch) => {
        const next = { ...search, ...patch };
        setSearch(next);
        spy(next);
      }}
      onClear={() => {
        const next = viewSearch('mine');
        setSearch(next);
        spy(next);
      }}
    />
  );
}

beforeEach(() => {
  server.use(getListUsersMockHandler(USERS), getListPartnersMockHandler(PARTNERS));
});

describe('FilterBar', () => {
  it('filters by status from a chip and names the choice on the chip', async () => {
    const spy = vi.fn();
    renderWithQuery(<Harness initial={parseQueueSearch({ view: 'x', mine: true })} spy={spy} />);
    await userEvent.click(screen.getByRole('button', { name: 'Status' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'In review' }));
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['in_review'], mine: true }));
    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Status: In review' })).toBeInTheDocument();
  });

  it("shows a queue view's statuses on its Status chip", () => {
    renderWithQuery(<Harness initial={viewSearch('rereview')} spy={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Status: Needs re-review' })).toBeInTheDocument();
  });

  it('clears one chip without touching the others', async () => {
    const spy = vi.fn();
    renderWithQuery(
      <Harness
        initial={parseQueueSearch({
          view: 'mine',
          mine: true,
          risk_tier: ['high'],
          product: ['credit_card'],
        })}
        spy={spy}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Clear Risk filter' }));
    const last = spy.mock.lastCall?.[0] as QueueSearch;
    expect(last.risk_tier).toBeUndefined();
    expect(last.product).toEqual(['credit_card']);
  });

  it('picks one assignee: me, unassigned, or a person', async () => {
    const spy = vi.fn();
    renderWithQuery(
      <Harness initial={parseQueueSearch({ view: 'active', status: ['in_review'] })} spy={spy} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Assignee' }));
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Sam Okafor' }));
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ assignee_id: [3], mine: undefined, unassigned: undefined }),
    );

    await userEvent.click(screen.getByRole('button', { name: 'Assignee: Sam Okafor' }));
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Unassigned' }));
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ unassigned: true, assignee_id: undefined, mine: undefined }),
    );
  });

  it('lists partners from the API', async () => {
    const spy = vi.fn();
    renderWithQuery(<Harness initial={viewSearch('mine')} spy={spy} />);
    await userEvent.click(screen.getByRole('button', { name: 'Partner' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'RateRadar' }));
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ partner_id: [13] }));
  });

  it('searches title or key after typing stops', async () => {
    const spy = vi.fn();
    renderWithQuery(<Harness initial={viewSearch('mine')} spy={spy} />);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the queue' }), 'CP-1044');
    await waitFor(() => {
      expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'CP-1044' }));
    });
  });

  it('changes the server sort from the sort menu', async () => {
    const onChange = vi.fn();
    renderWithQuery(<SortMenu sort="queue" onChange={onChange} />);
    await userEvent.click(screen.getByRole('button', { name: 'Sort: Queue order' }));
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Oldest first' }));
    expect(onChange).toHaveBeenLastCalledWith('oldest');
  });

  it('offers every server sort, each column both ways', async () => {
    renderWithQuery(<SortMenu sort="risk_tier_desc" onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Sort: Risk, high to low' }));
    const options = await screen.findAllByRole('menuitemradio');
    expect(options).toHaveLength(Object.keys(ItemSort).length);
    expect(screen.getByRole('menuitemradio', { name: 'Risk, high to low' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('menuitemradio', { name: 'Most findings first' })).toBeInTheDocument();
  });

  it('offers Clear filters only when filters beyond the view are set, and resets to the view', async () => {
    const spy = vi.fn();
    const { unmount } = renderWithQuery(<Harness initial={viewSearch('mine')} spy={spy} />);
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull();
    unmount();

    renderWithQuery(
      <Harness initial={{ ...viewSearch('mine'), risk_tier: ['high'], channel: ['email'] }} spy={spy} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(spy).toHaveBeenLastCalledWith(viewSearch('mine'));
  });

  it('keeps less-used filters under More filters until they have a value', async () => {
    const spy = vi.fn();
    renderWithQuery(<Harness initial={viewSearch('mine')} spy={spy} />);
    expect(screen.queryByRole('button', { name: /^Product/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'More filters' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Product' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Credit card' }));
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ product: ['credit_card'] }));
    // The menu keeps its list while open: the submenu holding focus stays mounted, so a second pick works and
    // each Escape lands in a menu (submenu, then root). Product joins the bar once the menu closes.
    expect(screen.getByRole('menuitem', { name: 'Product' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Personal loan' }));
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ product: ['credit_card', 'personal_loan'] }),
    );
    await userEvent.keyboard('{Escape}{Escape}');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('button', { name: /^Product: Credit card, Personal loan/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'More filters' }));
    expect(await screen.findByRole('menu', { name: 'More filters' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Product' })).toBeNull();
  });
});
