import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import type { ExportIn, ItemRowOut, SearchHitOut } from '../../api/generated/model';
import {
  APPROVED_ROWS,
  exportJob,
  LIBRARY_PARTNERS,
  ME_LIBRARY_MARKETER,
  ME_LIBRARY_REVIEWER,
  PRECEDENT_HITS,
  searchResults,
} from '../../test/fixtures/library';
import { renderApp, searchString } from '../../test/renderApp';
import { server } from '../../test/server';

const listRequests: URL[] = [];
const searchRequests: URL[] = [];

function serveLibrary(rows: ItemRowOut[], next_cursor: string | null = null) {
  server.use(
    http.get('*/api/library', ({ request }) => {
      listRequests.push(new URL(request.url));
      return HttpResponse.json({ rows, next_cursor });
    }),
  );
}

function serveSearch(hits: SearchHitOut[]) {
  server.use(
    http.get('*/api/library/search', ({ request }) => {
      const url = new URL(request.url);
      searchRequests.push(url);
      return HttpResponse.json(
        searchResults(
          hits,
          url.searchParams.get('query') ?? '',
          url.searchParams.get('mode') === 'text' ? 'text' : 'phrase',
        ),
      );
    }),
  );
}

beforeEach(() => {
  listRequests.length = 0;
  searchRequests.length = 0;
  server.use(getGetMeMockHandler(ME_LIBRARY_REVIEWER), getListPartnersMockHandler(LIBRARY_PARTNERS));
});

describe('Library: approved to run', () => {
  it('opens to the approved view and lists what may run now, legacy included', async () => {
    serveLibrary(APPROVED_ROWS);
    renderApp('/library');

    const table = await screen.findByRole('table', { name: 'Approved to run' });
    expect(screen.getByRole('tab', { name: 'Approved to run' })).toHaveAttribute('aria-selected', 'true');
    const link = within(table).getByRole('link', { name: /Holiday personal loan email/ });
    expect(link).toHaveAttribute('href', '/items/1088');
    expect(listRequests[0]?.searchParams.get('scope')).toBe('approved_to_run');

    const legacy = within(table).getByRole('row', { name: /CP-412/ });
    expect(within(legacy).getByText('Legacy')).toBeInTheDocument();
    expect(within(legacy).getByText('No pack · legacy')).toBeInTheDocument();
    expect(within(legacy).queryByRole('button', { name: /evidence pack/i })).toBeNull();
  });

  it('writes filters to the URL and sends them to the API', async () => {
    serveLibrary(APPROVED_ROWS);
    const { router } = renderApp('/library');
    await screen.findByRole('table', { name: 'Approved to run' });

    await userEvent.click(screen.getByRole('button', { name: 'Product' }));
    await userEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Credit card' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ product: ['credit_card'] });
    });
    await waitFor(() => {
      expect(listRequests.at(-1)?.searchParams.getAll('product')).toEqual(['credit_card']);
    });
  });

  it('says why the view is empty and offers to clear filters', async () => {
    serveLibrary([]);
    const { router } = renderApp(`/library${searchString({ channel: ['sms'] })}`);
    const heading = await screen.findByRole('heading', { name: 'No approved items match these filters' });
    const empty = heading.closest('.app-empty');
    if (!(empty instanceof HTMLElement)) throw new Error('no empty state');
    await userEvent.click(within(empty).getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => {
      expect(router.state.location.search).not.toHaveProperty('channel');
    });
  });

  it('shows the error with Retry', async () => {
    server.use(
      http.get('*/api/library', () =>
        HttpResponse.json({ code: 'server_error', message: 'The library is unavailable.' }, { status: 503 }),
      ),
    );
    renderApp('/library');
    expect(await screen.findByRole('heading', { name: "Couldn't load the library" })).toBeInTheDocument();
    expect(screen.getByText('The library is unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('exports the filtered view: POST /exports, poll until ready, then a download link', async () => {
    serveLibrary(APPROVED_ROWS);
    const posted: ExportIn[] = [];
    let polls = 0;
    server.use(
      http.post('*/api/exports', async ({ request }) => {
        posted.push((await request.json()) as ExportIn);
        return HttpResponse.json(exportJob({ id: 9 }), { status: 202 });
      }),
      http.get('*/api/exports/9', () => {
        polls += 1;
        return HttpResponse.json(
          polls < 2
            ? exportJob({ id: 9, status: 'running' })
            : exportJob({
                id: 9,
                status: 'ready',
                item_count: 8,
                filename: 'clearpath-export-2026-10-24.xlsx',
                download_url: '/api/exports/9/download',
              }),
        );
      }),
    );
    renderApp(`/library${searchString({ channel: ['email'] })}`);
    await screen.findByRole('table', { name: 'Approved to run' });

    await userEvent.click(screen.getByRole('button', { name: 'Export' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /Export view \(\.xlsx\)/ }));

    expect(await screen.findByText(/Building export/)).toBeInTheDocument();
    const download = await screen.findByRole('link', { name: /Download/ }, { timeout: 4000 });
    expect(download).toHaveAttribute('href', '/api/exports/9/download');
    expect(screen.getByText('8 items')).toBeInTheDocument();
    expect(posted).toEqual([
      {
        filters: { channel: ['email'], status: ['approved'] },
        sort: 'updated',
        include_evidence_packs: false,
      },
    ]);
  });

  it('says in one line why an export failed', async () => {
    serveLibrary(APPROVED_ROWS);
    server.use(
      http.post('*/api/exports', () => HttpResponse.json(exportJob({ id: 10 }), { status: 202 })),
      http.get('*/api/exports/10', () =>
        HttpResponse.json(
          exportJob({ id: 10, status: 'failed', error: 'The export ran out of time. Try a narrower view.' }),
        ),
      ),
    );
    renderApp('/library');
    await screen.findByRole('table', { name: 'Approved to run' });
    await userEvent.click(screen.getByRole('button', { name: 'Export' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /with evidence packs/ }));
    expect(await screen.findByText('The export ran out of time. Try a narrower view.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry export' })).toBeInTheDocument();
  });

  it('hides Export from marketers (the server refuses them)', async () => {
    server.use(getGetMeMockHandler(ME_LIBRARY_MARKETER));
    serveLibrary(APPROVED_ROWS);
    renderApp('/library');
    await screen.findByRole('table', { name: 'Approved to run' });
    expect(screen.queryByRole('button', { name: 'Export' })).toBeNull();
  });

  it('builds an evidence pack and offers the download', async () => {
    serveLibrary(APPROVED_ROWS);
    server.use(
      http.post('*/api/items/1088/evidence-pack', () =>
        HttpResponse.json(exportJob({ id: 31, kind: 'evidence_pack', item_id: 1088 }), { status: 202 }),
      ),
      http.get('*/api/exports/31', () =>
        HttpResponse.json(
          exportJob({
            id: 31,
            kind: 'evidence_pack',
            item_id: 1088,
            status: 'ready',
            item_count: 1,
            filename: 'CP-1088-evidence-pack-2026-10-24.zip',
            download_url: '/api/exports/31/download',
          }),
        ),
      ),
    );
    renderApp('/library');
    const row = await screen.findByRole('row', { name: /CP-1088/ });
    await userEvent.click(within(row).getByRole('button', { name: 'Evidence pack for CP-1088' }));
    const link = await within(row).findByRole('link', { name: 'Download evidence pack for CP-1088' });
    expect(link).toHaveAttribute('href', '/api/exports/31/download');
  });

  it("shows the server's reason when an item has no evidence pack (409)", async () => {
    serveLibrary(APPROVED_ROWS);
    server.use(
      http.post('*/api/items/1081/evidence-pack', () =>
        HttpResponse.json(
          { code: 'conflict', message: 'CP-1081 has no approval yet; an evidence pack records one.' },
          { status: 409 },
        ),
      ),
    );
    renderApp('/library');
    const row = await screen.findByRole('row', { name: /CP-1081/ });
    await userEvent.click(within(row).getByRole('button', { name: 'Evidence pack for CP-1081' }));
    expect(
      await within(row).findByText('CP-1081 has no approval yet; an evidence pack records one.'),
    ).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Evidence pack for CP-1081' })).toBeNull();
  });
});

describe('Library: precedents', () => {
  it('switches views through the URL', async () => {
    serveLibrary(APPROVED_ROWS);
    const { router } = renderApp('/library');
    await screen.findByRole('table', { name: 'Approved to run' });

    await userEvent.click(screen.getByRole('tab', { name: 'Precedents' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ tab: 'precedents' });
    });
    expect(await screen.findByRole('heading', { name: 'Search past approvals' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Export' })).toBeNull();
    expect(searchRequests).toHaveLength(0);
  });

  it('searches in phrase mode and highlights the matched wording, never as HTML', async () => {
    serveSearch(PRECEDENT_HITS);
    const { router } = renderApp(`/library${searchString({ tab: 'precedents' })}`);

    await userEvent.type(
      await screen.findByRole('searchbox', { name: 'Search approved copy' }),
      "won't affect your credit score",
    );
    const list = await screen.findByRole('list', { name: 'Precedents' });
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ query: "won't affect your credit score" });
    });
    expect(searchRequests.at(-1)?.searchParams.get('mode')).toBe('phrase');
    expect(searchRequests.at(-1)?.searchParams.get('query')).toBe("won't affect your credit score");

    const marks = list.querySelectorAll('mark');
    expect(marks).toHaveLength(3);
    expect(marks[0]?.textContent).toBe("won't affect your credit score");

    const first = within(list).getAllByRole('listitem')[0];
    if (first === undefined) throw new Error('no hit');
    expect(within(first).getByText('Matched v3')).toBeInTheDocument();
    expect(within(first).getByText('Approved with edits')).toBeInTheDocument();
    expect(within(first).getByRole('link', { name: /Holiday personal loan email/ })).toHaveAttribute(
      'href',
      '/items/1088',
    );

    // Precedent value doesn't lapse, run-permission does: the current status sits beside the matched outcome.
    const lapsed = within(list).getAllByRole('listitem')[1];
    if (lapsed === undefined) throw new Error('no hit');
    expect(within(lapsed).getByText('Re-review')).toBeInTheDocument();
    expect(within(lapsed).getByText('Approved')).toBeInTheDocument();
  });

  it('switches to text mode through the toggle', async () => {
    serveSearch(PRECEDENT_HITS);
    const { router } = renderApp(`/library${searchString({ tab: 'precedents', query: 'credit score' })}`);
    await screen.findByRole('list', { name: 'Precedents' });

    await userEvent.click(screen.getByRole('radio', { name: 'Text' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ mode: 'text' });
    });
    await waitFor(() => {
      expect(searchRequests.at(-1)?.searchParams.get('mode')).toBe('text');
    });
    expect(screen.getByText(/any order/)).toBeInTheDocument();
  });

  it('offers text mode when a phrase finds nothing', async () => {
    serveSearch([]);
    const { router } = renderApp(
      `/library${searchString({ tab: 'precedents', query: 'pre-approved today' })}`,
    );
    expect(
      await screen.findByRole('heading', { name: 'No precedents for “pre-approved today”' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try text mode' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ mode: 'text' });
    });
  });

  it('shows a search error with Retry', async () => {
    server.use(
      http.get('*/api/library/search', () =>
        HttpResponse.json(
          { code: 'server_error', message: 'Search is unavailable right now.' },
          { status: 503 },
        ),
      ),
    );
    renderApp(`/library${searchString({ tab: 'precedents', query: 'as low as' })}`);
    expect(await screen.findByRole('heading', { name: "Couldn't search precedents" })).toBeInTheDocument();
    expect(screen.getByText('Search is unavailable right now.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
