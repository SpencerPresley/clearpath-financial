import '@fontsource-variable/inter/wght.css';
import '../../theme/theme.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-react';

import { routeTree } from '../../routeTree.gen';
import { stubApi } from '../../test/browserApi';
import { PREVIEW_HEADING_ID } from './PreviewDrawer';
import { SIZES_KEY } from './QueueTable';

async function renderApp(path = '/queue') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: { queryClient },
  });
  const screen = await render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { screen, router };
}

function must<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`missing ${what}`);
  return value;
}

beforeEach(async () => {
  await page.viewport(1440, 900);
  stubApi();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

it('moves real focus with j/k and into the preview with Enter', async () => {
  const { screen } = await renderApp();
  await expect.element(screen.getByText('RateRadar lead-gen form copy')).toBeVisible();

  await userEvent.keyboard('j');
  expect(document.activeElement?.tagName).toBe('TR');
  expect(document.activeElement?.textContent).toContain('CP-1031');
  await userEvent.keyboard('j');
  expect(document.activeElement?.textContent).toContain('CP-1038');

  await userEvent.keyboard('{Enter}');
  await expect.element(screen.getByRole('complementary', { name: 'Preview CP-1038' })).toBeVisible();
  await expect.poll(() => document.activeElement?.id).toBe(PREVIEW_HEADING_ID);

  // j still moves through the queue with the drawer open, and the drawer follows.
  await userEvent.keyboard('j');
  await expect.element(screen.getByRole('complementary', { name: 'Preview CP-1044' })).toBeVisible();
});

it('draws a visible focus ring on the focused row', async () => {
  const { screen } = await renderApp();
  await expect.element(screen.getByText('RateRadar lead-gen form copy')).toBeVisible();
  await userEvent.keyboard('j');
  const cell = must(document.activeElement?.querySelector('td'), 'focused cell');
  expect(getComputedStyle(cell).boxShadow).toContain('inset');
});

it('resizes a column by dragging its edge and remembers the width', async () => {
  const { screen } = await renderApp();
  await expect.element(screen.getByText('RateRadar lead-gen form copy')).toBeVisible();
  const th = must(document.querySelector<HTMLElement>('th[data-column="partner"]'), 'partner header');
  const handle = must(th.querySelector<HTMLElement>('.app-th-resize'), 'resize handle');
  const before = th.getBoundingClientRect().width;
  const box = handle.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;

  handle.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
  document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: x + 60, clientY: y }));
  document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x + 60, clientY: y }));

  await expect.poll(() => Math.round(th.getBoundingClientRect().width - before)).toBeGreaterThanOrEqual(55);
  expect(JSON.parse(window.localStorage.getItem(SIZES_KEY) ?? '{}')).toHaveProperty('partner');
});

it('keeps the page from scrolling sideways at 1280px with the drawer open', async () => {
  await page.viewport(1280, 800);
  const { screen } = await renderApp('/queue?item=1047');
  await expect.element(screen.getByRole('complementary', { name: 'Preview CP-1047' })).toBeVisible();
  await expect.element(screen.getByTitle('RateRadar lead-gen form copy')).toBeVisible();
  const main = must(document.querySelector('main'), 'main');
  expect(main.scrollWidth).toBeLessThanOrEqual(main.clientWidth);
  const rowHeight = must(document.querySelector('tr.app-tr'), 'row').getBoundingClientRect().height;
  expect(Math.round(rowHeight)).toBe(36);
});
