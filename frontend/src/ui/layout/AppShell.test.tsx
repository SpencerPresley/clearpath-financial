import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { routeTree } from '../../routeTree.gen';
import { server } from '../../test/server';
import type { Role } from '../domain';
import { NAV_COLLAPSED_KEY } from './AppShell';
import { ViewerProvider } from './Viewer';

function renderApp({ roles, path = '/' }: { roles?: readonly Role[]; path?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: { queryClient },
  });
  const app = <RouterProvider router={router} />;
  return render(
    <QueryClientProvider client={queryClient}>
      {roles === undefined ? (
        app
      ) : (
        <ViewerProvider viewer={{ name: 'Test User', roles, isDemo: false }}>{app}</ViewerProvider>
      )}
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
    const library = within(nav).getByRole('link', { name: 'Library, soon' });
    expect(library).toHaveAttribute('aria-disabled', 'true');
    expect(library.tagName).not.toBe('A');
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

  it('opens the account panel and says plainly that sign-in is not wired yet', async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole('button', { name: /Demo user/ }));
    const panel = await screen.findByRole('dialog', { name: 'Account' });
    expect(panel).toHaveTextContent('No sign-in yet');
    // No inert "Sign out": the action doesn't exist until accounts do.
    expect(within(panel).queryByText('Sign out')).toBeNull();
  });

  it('keeps unbuilt sections reachable by keyboard and named in the collapsed rail', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(NAV_COLLAPSED_KEY, 'true');
    renderApp();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    const library = within(nav).getByRole('link', { name: 'Library, soon' });
    expect(library).toHaveAttribute('aria-disabled', 'true');
    expect(library).not.toHaveAttribute('href');
    for (let i = 0; i < 20 && document.activeElement !== library; i += 1) await user.tab();
    expect(library).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Library · Soon');
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
