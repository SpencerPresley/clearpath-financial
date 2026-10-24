import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { JUMP_ROWS, jumpResults } from '../../test/fixtures/search';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { QuickJump, RESULT_LIMIT } from './QuickJump';

/** Serves `GET /items?q=` like the API and records each query it was asked. */
function serveItems() {
  const asked: URLSearchParams[] = [];
  server.use(
    http.get('*/api/items', ({ request }) => {
      const params = new URL(request.url).searchParams;
      asked.push(params);
      const rows = jumpResults(params.get('q') ?? '');
      return HttpResponse.json({ rows, next_cursor: null, total: rows.length });
    }),
  );
  return asked;
}

function renderJump() {
  const root = createRootRoute({
    component: () => (
      <>
        <QuickJump />
        <input aria-label="Some other field" />
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

const box = () => screen.getByRole('combobox', { name: 'Jump to item' });

/** Result rows only: React Aria wraps the empty state in an option too, so wait for the items' keys. */
async function results(count: number) {
  const list = await screen.findByRole('listbox');
  await waitFor(() => {
    expect(
      within(list)
        .getAllByRole('option')
        .filter((o) => /CP-\d+/.test(o.textContent)),
    ).toHaveLength(count);
  });
  return within(list).getAllByRole('option');
}

describe('QuickJump', () => {
  it('finds items by title across every status, legacy included, and shows key, title and status', async () => {
    const user = userEvent.setup();
    const asked = serveItems();
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'fall');

    const options = await results(4);
    expect(options[0]).toHaveTextContent('CP-1042');
    expect(options[0]).toHaveTextContent('Fall personal loan promo — paid social');
    expect(options[0]).toHaveTextContent('In review');
    expect(options[2]).toHaveTextContent('MCR-26-045');
    // Debounced: one request for the settled text, not one per keystroke. Not the queue sort, which would
    // leave out approved and legacy items.
    const last = asked.at(-1);
    expect(asked.map((p) => p.get('q'))).toEqual(['fall']);
    expect(last?.get('sort')).toBe('updated');
    expect(last?.get('limit')).toBe(String(RESULT_LIMIT));
  });

  it('opens the top result on Enter, and clears the box', async () => {
    const user = userEvent.setup();
    serveItems();
    const { router } = renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'CP-1042');
    await screen.findByRole('option', { name: /CP-1042/ });
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
    expect(box()).toHaveValue('');
  });

  it('never opens an answer to an older search: Enter waits for what is typed now', async () => {
    const user = userEvent.setup();
    serveItems();
    const { router } = renderJump();
    const input = await screen.findByRole('combobox', { name: 'Jump to item' });

    await user.type(input, 'fall');
    await results(4);
    // Keep typing and press Enter before the debounce fires: "fall"'s top row (CP-1042) must not open.
    await user.type(input, ' promo landing{Enter}');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1070');
    });
  });

  it('opens the top result when Enter comes before the results do', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/items', async ({ request }) => {
        await delay(300);
        const rows = jumpResults(new URL(request.url).searchParams.get('q') ?? '');
        return HttpResponse.json({ rows, next_cursor: null, total: rows.length });
      }),
    );
    const { router } = renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'CP-1042{Enter}');
    expect(router.state.location.pathname).toBe('/');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
  });

  it('says why the list is empty to a screen reader, not just "0 options"', async () => {
    const user = userEvent.setup();
    serveItems();
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'zzz');

    await waitFor(() => {
      expect(screen.getAllByRole('status').some((s) => s.textContent === 'No items match “zzz”.')).toBe(true);
    });
  });

  it('Escape clears the box and returns focus to where ⌘K took it from', async () => {
    const user = userEvent.setup();
    serveItems();
    renderJump();
    const other = await screen.findByRole('textbox', { name: 'Some other field' });

    await user.click(other);
    await user.keyboard('{Control>}k{/Control}');
    await user.keyboard('fall');
    await results(4);
    await user.keyboard('{Escape}');

    expect(other).toHaveFocus();
    expect(box()).toHaveValue('');
  });

  it('opens the highlighted result', async () => {
    const user = userEvent.setup();
    serveItems();
    const { router } = renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'fall');
    await results(4);
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1061');
    });
  });

  it('finds a legacy item by its old tracker ID', async () => {
    const user = userEvent.setup();
    serveItems();
    const { router } = renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'MCR-26-045');
    const option = await screen.findByRole('option', { name: /CP-1188/ });
    expect(option).toHaveTextContent('MCR-26-045');
    await user.click(option);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1188');
    });
  });

  it('asks for a little more before searching on one character', async () => {
    const user = userEvent.setup();
    const asked = serveItems();
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'f');

    expect(
      await within(await screen.findByRole('listbox')).findByText(
        'Type a CP key, title words or tracker ID.',
      ),
    ).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(asked).toHaveLength(0);
  });

  it('says when nothing matches', async () => {
    const user = userEvent.setup();
    serveItems();
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'zzz');

    expect(
      await within(await screen.findByRole('listbox')).findByText('No items match “zzz”.'),
    ).toBeInTheDocument();
  });

  it('shows that it is searching', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/items', async () => {
        await delay('infinite');
        return HttpResponse.json({ rows: JUMP_ROWS, next_cursor: null, total: 4 });
      }),
    );
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'fall');

    expect(await within(await screen.findByRole('listbox')).findByText('Searching…')).toBeInTheDocument();
  });

  it('says what went wrong when the search fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/items', () =>
        HttpResponse.json(
          { code: 'server_error', message: 'Search is temporarily unavailable.' },
          { status: 503 },
        ),
      ),
    );
    renderJump();

    await user.type(await screen.findByRole('combobox', { name: 'Jump to item' }), 'fall');

    expect(
      await within(await screen.findByRole('listbox')).findByText('Search is temporarily unavailable.'),
    ).toBeInTheDocument();
  });

  it('takes focus on ⌘K and Ctrl+K from anywhere, and on / outside a field', async () => {
    const user = userEvent.setup();
    serveItems();
    renderJump();
    const other = await screen.findByRole('textbox', { name: 'Some other field' });

    await user.click(other);
    await user.keyboard('/');
    expect(other).toHaveFocus(); // typing a slash in a field stays typing
    await user.keyboard('{Meta>}k{/Meta}');
    expect(box()).toHaveFocus();

    await user.click(other);
    await user.keyboard('{Control>}k{/Control}');
    expect(box()).toHaveFocus();

    other.blur();
    await user.keyboard('/');
    expect(box()).toHaveFocus(); // (that the slash isn't typed into the box is checked in a real browser, e2e)
    expect(box()).toHaveAttribute('aria-keyshortcuts', 'Meta+K Control+K /');
  });
});
