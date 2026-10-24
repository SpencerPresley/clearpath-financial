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

function headers(): string[] {
  return [...document.querySelectorAll<HTMLElement>('table[aria-label="Queue"] thead th')].map(
    (th) => th.dataset.column ?? '',
  );
}

function region(): HTMLElement {
  return must(document.querySelector<HTMLElement>('.app-queue-region'), 'queue region');
}

function titleWidth(): number {
  const th = must(document.querySelector('th[data-column="title"]'), 'title header');
  return th.getBoundingClientRect().width;
}

// Walkthrough-1 nit 3: narrow layouts keep the triage columns and give the title what's left.
it.each([
  [1440, 900, '/queue?item=1047', 'the drawer open'],
  [1280, 800, '/queue', 'nothing open'],
  [1280, 800, '/queue?item=1047', 'the drawer open'],
])('keeps Risk and Assignee at %ix%i with %s, without sideways scrolling', async (w, h, path) => {
  await page.viewport(w, h);
  const { screen } = await renderApp(path);
  await expect.element(screen.getByTitle('RateRadar lead-gen form copy')).toBeVisible();

  await expect.poll(headers).toEqual(expect.arrayContaining(['risk_tier', 'assignee', 'status', 'title']));
  expect(region().scrollWidth).toBeLessThanOrEqual(region().clientWidth);
  expect(titleWidth()).toBeGreaterThanOrEqual(180);
});

it('at 1280 with nothing open, tightens instead of dropping columns, and the title has room', async () => {
  await page.viewport(1280, 800);
  const { screen } = await renderApp('/queue');
  await expect.element(screen.getByTitle('RateRadar lead-gen form copy')).toBeVisible();
  await expect
    .poll(headers)
    .toEqual([
      'select',
      'key',
      'title',
      'status',
      'risk_tier',
      'partner',
      'assignee',
      'open_findings',
      'age',
      'round',
    ]);
  expect(titleWidth()).toBeGreaterThanOrEqual(240);
});

/** Whether a pointer at (dx, dy) from the element's center lands on it. */
function hitsAt(el: Element, dx: number, dy: number): boolean {
  const box = el.getBoundingClientRect();
  const target = document.elementFromPoint(box.left + box.width / 2 + dx, box.top + box.height / 2 + dy);
  return target !== null && el.contains(target);
}

// Walkthrough-1 nit 17: 40px hit areas on small frequent controls, without growing what you see.
it('gives the bell and the shortcuts button a 40x40 hit area at their visible size', async () => {
  const { screen } = await renderApp('/queue');
  await expect.element(screen.getByText('RateRadar lead-gen form copy')).toBeVisible();
  for (const name of ['Notifications', 'Keyboard shortcuts (?)']) {
    const el = must(document.querySelector(`[aria-label^="${name}"]`), name);
    const box = el.getBoundingClientRect();
    expect(Math.max(box.width, box.height)).toBeLessThanOrEqual(32);
    for (const [dx, dy] of [
      [-19, 0],
      [19, 0],
      [0, -19],
      [0, 19],
    ] as const) {
      expect(hitsAt(el, dx, dy), `${name} at ${String(dx)},${String(dy)}`).toBe(true);
    }
  }
});

it('gives a filter chip clear 40px of height without taking the chip button’s clicks', async () => {
  const { screen } = await renderApp('/queue?product=%5B%22personal_loan%22%5D');
  await expect.element(screen.getByRole('button', { name: 'Clear Product filter' })).toBeVisible();
  const clear = must(document.querySelector('[aria-label="Clear Product filter"]'), 'clear');
  expect(clear.getBoundingClientRect().height).toBeLessThanOrEqual(28);
  expect(hitsAt(clear, 0, -19)).toBe(true);
  expect(hitsAt(clear, 0, 19)).toBe(true);
  const chipButton = must(clear.parentElement?.querySelector('.app-chip-btn'), 'chip button');
  const box = clear.getBoundingClientRect();
  const left = document.elementFromPoint(box.left - 2, box.top + box.height / 2);
  expect(left !== null && chipButton.contains(left)).toBe(true);
});

it('makes the row checkbox hit area the whole 40px select cell', async () => {
  const { screen } = await renderApp('/queue');
  await expect.element(screen.getByText('RateRadar lead-gen form copy')).toBeVisible();
  const label = must(document.querySelector('tbody .app-check-hit'), 'checkbox label');
  expect(Math.round(label.getBoundingClientRect().width)).toBe(40);
});
