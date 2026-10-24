import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { NotificationOut, NotificationPageOut } from '../../api/generated/model';
import { INBOX_ROWS, EMPTY_PAGE, pageOf } from '../../test/fixtures/notifications';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { ToastHost } from '../../ui/toast';
import { NotificationBell, countLabel } from './NotificationBell';
import { POLL_MS } from './useNotifications';

// Local noon, so "Today" doesn't depend on the machine's timezone.
const NOW = new Date(2026, 9, 24, 12, 0);
const local = (day: number, hour: number, minute = 0) => new Date(2026, 9, day, hour, minute).toISOString();

// INBOX_ROWS re-timed in local time: three today (unread), three earlier (read).
const TIMES = [
  local(24, 11, 48),
  local(24, 10, 5),
  local(24, 6, 30),
  local(23, 16),
  local(22, 6),
  local(20, 11),
];
const ROWS: NotificationOut[] = INBOX_ROWS.map((row, i) => ({
  ...row,
  created_at: TIMES[i] ?? row.created_at,
}));

/** Serves a mutable inbox and records writes, like the API would. */
function serveInbox(initial: NotificationPageOut) {
  let page = structuredClone(initial);
  const posted: string[] = [];
  const gets = { count: 0 };
  server.use(
    http.get('*/api/notifications', () => {
      gets.count += 1;
      return HttpResponse.json(page);
    }),
    http.post('*/api/notifications/read-all', () => {
      posted.push('read-all');
      const marked = page.unread_count;
      page = {
        rows: page.rows.map((r) => ({ ...r, read_at: r.read_at ?? NOW.toISOString() })),
        unread_count: 0,
      };
      return HttpResponse.json({ marked });
    }),
    http.post('*/api/notifications/:id/read', ({ params }) => {
      const id = Number(params.id);
      posted.push(`read ${String(id)}`);
      page = {
        rows: page.rows.map((r) => (r.id === id ? { ...r, read_at: NOW.toISOString() } : r)),
        unread_count: page.rows.filter((r) => r.read_at === null && r.id !== id).length,
      };
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { posted, gets };
}

/** The bell in a root layout, like the shell's topbar, so it stays mounted when a row navigates. */
function renderBell() {
  const root = createRootRoute({
    component: () => (
      <>
        <NotificationBell />
        <ToastHost />
        <Outlet />
      </>
    ),
  });
  const home = createRoute({ getParentRoute: () => root, path: '/', component: () => <p>Queue</p> });
  const review = createRoute({
    getParentRoute: () => root,
    path: '/items/$itemId',
    component: () => <p>Review screen</p>,
  });
  const router = createRouter({
    routeTree: root.addChildren([home, review]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  return { router, ...renderWithQuery(<RouterProvider router={router} />) };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('NotificationBell', () => {
  it('shows the unread count on the bell and says it in the name', async () => {
    serveInbox(pageOf(ROWS));
    renderBell();

    const bell = await screen.findByRole('button', { name: 'Notifications, 3 unread' });
    expect(within(bell).getByText('3')).toBeInTheDocument();
  });

  it('has no count when everything is read', async () => {
    serveInbox(EMPTY_PAGE);
    renderBell();

    const bell = await screen.findByRole('button', { name: 'Notifications' });
    await waitFor(() => {
      expect(bell.textContent).toBe('');
    });
  });

  it('caps the count at 99+', () => {
    expect(countLabel(7)).toBe('7');
    expect(countLabel(99)).toBe('99');
    expect(countLabel(140)).toBe('99+');
  });

  it('lists notifications newest first, grouped Today and Earlier, in domain language', async () => {
    const user = userEvent.setup();
    serveInbox(pageOf(ROWS));
    renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }));
    const dialog = await screen.findByRole('dialog', { name: 'Notifications' });
    const list = within(dialog).getByRole('listbox', { name: 'Notifications' });
    const today = within(list).getByRole('group', { name: 'Today' });
    const earlier = within(list).getByRole('group', { name: 'Earlier' });

    expect(within(list).getAllByRole('group')).toEqual([today, earlier]);
    const todayRows = within(today).getAllByRole('option');
    expect(todayRows.map((row) => row.querySelector('.app-inbox-line')?.textContent)).toEqual([
      'Unread: Dana Reyes requested changes on CP-42 · Fall personal loan promo',
      'Unread: Sam Okafor mentioned you on CP-1042 · Spring balance transfer email',
      'Unread: Priya Raman assigned CP-1051 · LendRight comparison page to you',
    ]);
    expect(todayRows[0]).toHaveTextContent('12m');
    const earlierRows = within(earlier).getAllByRole('option');
    expect(earlierRows[0]).toHaveTextContent('CP-1007 · Debt consolidation landing page needs re-review');
    expect(earlierRows[1]).toHaveTextContent(
      'Approval for CP-988 · Home improvement loan banner expires Nov 23',
    );
    expect(earlierRows[0]).not.toHaveTextContent('Unread');
    expect(within(dialog).getByText('3 unread')).toBeInTheDocument();
  });

  it('marks a row read and opens the comment’s version when a mention is clicked', async () => {
    const user = userEvent.setup();
    const api = serveInbox(pageOf(ROWS));
    const { router } = renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }));
    await user.click(await screen.findByRole('option', { name: /Sam Okafor mentioned you/ }));

    expect(await screen.findByText('Review screen')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/items/1042');
    expect(router.state.location.search).toEqual({ tab: 'comments', v: 2 });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(api.posted).toEqual(['read 8']);
    });
    expect(await screen.findByRole('button', { name: 'Notifications, 2 unread' })).toBeInTheDocument();
  });

  it('opens a row from the keyboard', async () => {
    const user = userEvent.setup();
    const api = serveInbox(pageOf(ROWS));
    const { router } = renderBell();

    await screen.findByRole('button', { name: 'Notifications, 3 unread' });
    await user.tab();
    await user.keyboard('{Enter}');
    await screen.findByRole('dialog', { name: 'Notifications' });
    // Into the list (past Mark all read), then down to the assignment and open it.
    await user.tab();
    await user.tab();
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1051');
    });
    expect(api.posted).toEqual(['read 7']);
  });

  it('does not mark a read row again', async () => {
    const user = userEvent.setup();
    const api = serveInbox(pageOf(ROWS));
    const { router } = renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }));
    await user.click(await screen.findByRole('option', { name: /CP-1003/ }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1003');
    });
    expect(api.posted).toEqual([]);
  });

  it('marks everything read', async () => {
    const user = userEvent.setup();
    const api = serveInbox(pageOf(ROWS));
    renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }));
    const dialog = await screen.findByRole('dialog', { name: 'Notifications' });
    await user.click(within(dialog).getByRole('button', { name: 'Mark all read' }));

    expect(within(dialog).getByRole('button', { name: 'Mark all read' })).toBeDisabled();
    expect(within(dialog).queryByText(/Unread:/)).not.toBeInTheDocument();
    expect(api.posted).toEqual(['read-all']);
    // The open popover hides the page from assistive tech; the bell is still there underneath.
    expect(screen.getByRole('button', { name: 'Notifications', hidden: true })).toBeInTheDocument();
  });

  it('puts the rows back and says so when mark all read fails', async () => {
    const user = userEvent.setup();
    serveInbox(pageOf(ROWS));
    server.use(
      http.post('*/api/notifications/read-all', () =>
        HttpResponse.json({ code: 'server_error', message: 'Server error.' }, { status: 500 }),
      ),
    );
    renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }));
    const dialog = await screen.findByRole('dialog', { name: 'Notifications' });
    await user.click(within(dialog).getByRole('button', { name: 'Mark all read' }));

    expect(await screen.findByText('Couldn’t mark notifications read')).toBeInTheDocument();
    expect(within(dialog).getAllByText(/Unread:/)).toHaveLength(3);
  });

  it('says what shows up here when the inbox is empty', async () => {
    const user = userEvent.setup();
    serveInbox(EMPTY_PAGE);
    renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications' }));
    const dialog = await screen.findByRole('dialog', { name: 'Notifications' });

    expect(await within(dialog).findByRole('heading', { name: 'No notifications' })).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        'Assignments, decisions, re-reviews and @mentions on your items show up here.',
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Mark all read' })).toBeDisabled();
  });

  it('shows a loading placeholder until the first page arrives', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/notifications', async () => {
        await delay('infinite');
        return HttpResponse.json(EMPTY_PAGE);
      }),
    );
    renderBell();

    await user.click(await screen.findByRole('button', { name: 'Notifications' }));

    expect(await screen.findByRole('status', { name: 'Loading notifications' })).toBeInTheDocument();
  });

  it('keeps the bell quiet when loading fails, and offers Retry inside', async () => {
    const user = userEvent.setup();
    let fail = true;
    server.use(
      http.get('*/api/notifications', () =>
        fail
          ? HttpResponse.json({ code: 'server_error', message: 'Server error.' }, { status: 500 })
          : HttpResponse.json(pageOf(ROWS)),
      ),
    );
    renderBell();

    const bell = await screen.findByRole('button', { name: 'Notifications' });
    await user.click(bell);
    const alert = await within(await screen.findByRole('dialog')).findByRole('alert');
    expect(alert).toHaveTextContent('Notifications didn’t load. Server error.');
    expect(bell.textContent).toBe('');

    fail = false;
    await user.click(within(alert).getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('option', { name: /Dana Reyes requested changes/ })).toBeInTheDocument();
  });
});

describe('polling', () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });

  it('asks again every 30 seconds and picks up new notifications', async () => {
    const api = serveInbox(EMPTY_PAGE);
    renderBell();
    await screen.findByRole('button', { name: 'Notifications' });
    await waitFor(() => {
      expect(api.gets.count).toBe(1);
    });

    server.use(http.get('*/api/notifications', () => HttpResponse.json(pageOf(ROWS.slice(0, 1)))));
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS));

    expect(await screen.findByRole('button', { name: 'Notifications, 1 unread' })).toBeInTheDocument();
  });
});
