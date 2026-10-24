import '@fontsource-variable/inter/wght.css';
import '../../theme/theme.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-react';

import { routeTree } from '../../routeTree.gen';
import { stubApi } from '../../test/browserApi';

async function renderApp(path = '/') {
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

beforeEach(async () => {
  await page.viewport(1440, 900);
  stubApi(); // the root route resolves the viewer from /api/me
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

it('collapses the nav to its icon rail and back', async () => {
  const screen = await renderApp();
  const nav = screen.getByRole('navigation', { name: 'Primary' });
  await expect.element(nav).toBeVisible();
  const width = () => nav.element().getBoundingClientRect().width;
  await expect.poll(width).toBe(216);

  await screen.getByRole('button', { name: 'Collapse navigation' }).click();
  await expect.poll(width).toBe(52);

  await screen.getByRole('button', { name: 'Expand navigation' }).click();
  await expect.poll(width).toBe(216);
});

it('shows a visible focus ring on keyboard focus', async () => {
  const screen = await renderApp();
  await expect.element(screen.getByRole('button', { name: 'Collapse navigation' })).toBeVisible();

  await userEvent.tab(); // skip link
  const skip = screen.getByText('Skip to content');
  await expect.element(skip).toHaveFocus();
  await expect.element(skip).toBeVisible();

  await userEvent.tab(); // nav toggle
  const toggle = screen.getByRole('button', { name: 'Collapse navigation' }).element();
  expect(document.activeElement).toBe(toggle);
  const style = getComputedStyle(toggle);
  expect(style.outlineStyle).toBe('solid');
  expect(style.outlineWidth).toBe('2px');
});

it('renders the UI in Inter with tabular figures for ages', async () => {
  const screen = await renderApp('/dev/design');
  await expect.element(screen.getByRole('heading', { name: 'Design system' })).toBeVisible();
  await document.fonts.ready;
  expect(document.fonts.check('13px "Inter Variable"')).toBe(true);
  expect(getComputedStyle(document.documentElement).fontFamily).toContain('Inter Variable');

  const age = document.querySelector('time.app-age');
  if (age === null) throw new Error('no RelativeAge on the gallery');
  expect(getComputedStyle(age).fontVariantNumeric).toContain('tabular-nums');
});
