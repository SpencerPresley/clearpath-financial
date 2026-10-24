import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { getItemsMock } from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getPartnersMock } from '../../api/generated/partners/partners.msw';
import { getUsersMock } from '../../api/generated/users/users.msw';
import { routeTree } from '../../routeTree.gen';
import { server } from '../../test/server';
import type { Role } from '../domain';
import { NAV_COLLAPSED_KEY } from './AppShell';
import type { NavSection } from './nav';

// An unbuilt section, so the shell's "Soon" rendering stays covered now that every real section has a page.
vi.mock('./nav', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./nav')>();
  const reports: NavSection = {
    id: 'reports',
    label: 'Reports',
    icon: 'nav.metrics',
    group: 'operations',
    roles: 'everyone',
  };
  return {
    ...actual,
    navGroupsFor: (roles: readonly Role[]) =>
      actual
        .navGroupsFor(roles)
        .map((group) =>
          group.id === 'operations' ? { ...group, sections: [...group.sections, reports] } : group,
        ),
  };
});

const ALL_ROLES: Role[] = ['marketer', 'reviewer', 'lead', 'admin'];

function renderApp({ roles = ALL_ROLES, path = '/' }: { roles?: Role[]; path?: string } = {}) {
  // The shell's viewer comes from GET /api/me (SessionGate in the root route). The index route is the queue;
  // its lists get the generated mocks (these tests assert on the shell, not on queue data).
  server.use(
    ...getItemsMock(),
    ...getUsersMock(),
    ...getPartnersMock(),
    getGetMeMockHandler({
      id: 1,
      display_name: 'Test User',
      email: 'test@clearpath.test',
      roles,
      effective_roles: roles,
      is_available: true,
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: { queryClient },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
});

describe('AppShell', () => {
  it('renders the wordmark, primary nav, and the current page marked active', async () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));
    renderApp();

    expect(await screen.findByRole('link', { name: 'ClearPath Compliance Review' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: 'Queue' })).toHaveAttribute('aria-current', 'page');
  });

  it('shows unbuilt sections as disabled, not as links to placeholder pages', async () => {
    renderApp();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    // Every real section is built (the Outbox was the last), so these use the made-up one mocked in above.
    const reports = within(nav).getByRole('link', { name: 'Reports, soon' });
    expect(reports).toHaveAttribute('aria-disabled', 'true');
    expect(reports.tagName).not.toBe('A');
    expect(within(nav).getByRole('link', { name: 'Outbox' })).toHaveAttribute('href', '/outbox');
  });

  it('filters sections by the viewer roles', async () => {
    renderApp({ roles: ['marketer'] });
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).queryByText('Queue')).toBeNull();
    expect(within(nav).queryByText('Offer terms')).toBeNull();
    expect(within(nav).getByText('My submissions')).toBeInTheDocument();
  });

  it('shows search as visibly disabled until search ships', async () => {
    renderApp();
    const search = await screen.findByRole('searchbox', { name: 'Search items' });
    expect(search).toBeDisabled();
    expect(search).toHaveAttribute('placeholder', 'Search (soon)');
  });

  it('opens the account panel with the signed-in user, roles, and sign out', async () => {
    const user = userEvent.setup();
    renderApp({ roles: ['lead', 'reviewer'] });
    await user.click(await screen.findByRole('button', { name: 'Test User, account' }));
    const panel = await screen.findByRole('dialog', { name: 'Account' });
    expect(panel).toHaveTextContent('test@clearpath.test');
    expect(panel).toHaveTextContent('Compliance lead, Reviewer');
    expect(within(panel).getByRole('button', { name: 'Sign out' })).toBeEnabled();
  });

  it('signs out and returns to the sign-in form', async () => {
    const user = userEvent.setup();
    renderApp();
    let signedIn = true;
    server.use(
      http.delete('*/_allauth/browser/v1/auth/session', () => {
        signedIn = false;
        return HttpResponse.json({ status: 401 }, { status: 401 });
      }),
      http.get('*/api/me', () =>
        signedIn
          ? HttpResponse.json({
              id: 1,
              display_name: 'Test User',
              email: 'test@clearpath.test',
              roles: ['reviewer'],
              effective_roles: ['reviewer'],
              is_available: true,
            })
          : HttpResponse.json({ code: 'not_authenticated', message: 'Sign in.' }, { status: 401 }),
      ),
    );
    await user.click(await screen.findByRole('button', { name: 'Test User, account' }));
    await user.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('keeps unbuilt sections reachable by keyboard and named in the collapsed rail', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(NAV_COLLAPSED_KEY, 'true');
    renderApp();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    const reports = within(nav).getByRole('link', { name: 'Reports, soon' });
    expect(reports).toHaveAttribute('aria-disabled', 'true');
    expect(reports).not.toHaveAttribute('href');
    for (let i = 0; i < 30 && document.activeElement !== reports; i += 1) await user.tab();
    expect(reports).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Reports · Soon');
  });

  it('collapses the nav, keeps every item named, and remembers the choice', async () => {
    const user = userEvent.setup();
    renderApp();
    const toggle = await screen.findByRole('button', { name: 'Collapse navigation' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.click(toggle);

    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav).toHaveAttribute('data-collapsed', 'true');
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(within(nav).getByRole('link', { name: 'Queue' })).toBeInTheDocument();
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe('true');
  });

  it('starts collapsed when the saved preference says so', async () => {
    window.localStorage.setItem(NAV_COLLAPSED_KEY, 'true');
    renderApp();
    expect(await screen.findByRole('navigation', { name: 'Primary' })).toHaveAttribute(
      'data-collapsed',
      'true',
    );
  });
});

describe('API status in the shell', () => {
  it('is quiet when the API is up: no visible signal', async () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));
    renderApp();
    expect(await screen.findByText('Server connected')).toHaveClass('sr-only');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('is prominent when the API is down', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.json({ detail: 'down' }, { status: 503 })));
    renderApp();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Can't reach server · changes won't save");
  });
});
