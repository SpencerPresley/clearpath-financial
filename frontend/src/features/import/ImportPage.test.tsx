import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import type { ImportJobOut, ImportMappingIn, ImportPreviewOut } from '../../api/generated/model';
import {
  committedPreview,
  CUSTOM_COUNTS,
  CUSTOM_PROBLEMS,
  CUSTOM_ROWS,
  CUSTOM_UNMAPPED,
  importJob,
  importPreview,
  recentImports,
} from '../../test/fixtures/imports';
import { LIBRARY_PARTNERS, ME_ADMIN, ME_LIBRARY_REVIEWER } from '../../test/fixtures/library';
import { renderApp, searchString } from '../../test/renderApp';
import { server } from '../../test/server';

const mappings: ImportMappingIn[] = [];

function serveJob(
  job: ImportJobOut | (() => ImportJobOut),
  preview: ImportPreviewOut | (() => ImportPreviewOut),
) {
  server.use(
    http.get('*/api/imports/7', () => HttpResponse.json(typeof job === 'function' ? job() : job)),
    http.get('*/api/imports/7/preview', () =>
      HttpResponse.json(typeof preview === 'function' ? preview() : preview),
    ),
  );
}

beforeEach(() => {
  mappings.length = 0;
  server.use(
    getGetMeMockHandler(ME_ADMIN),
    getListPartnersMockHandler(LIBRARY_PARTNERS),
    http.get('*/api/imports', () => HttpResponse.json(recentImports())),
  );
});

describe('Import: start', () => {
  it('polls recent imports while one is committing, until it lands', async () => {
    let calls = 0;
    server.use(
      http.get('*/api/imports', () => {
        calls += 1;
        const [first, ...rest] = recentImports();
        if (first === undefined) throw new Error('fixture');
        const row =
          calls < 2 ? { ...first, status: 'committing' as const, summary: null, committed_at: null } : first;
        return HttpResponse.json([row, ...rest]);
      }),
    );
    renderApp('/import');
    const table = await screen.findByRole('table', { name: 'Recent imports' });
    expect(within(table).getByText('Importing')).toBeInTheDocument();
    expect(
      await within(table).findByText('178 created · 2 skipped', {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    const settled = calls;
    await new Promise((r) => setTimeout(r, 2500));
    expect(calls).toBe(settled);
  });

  it('is for admins only', async () => {
    server.use(getGetMeMockHandler(ME_LIBRARY_REVIEWER));
    renderApp('/import');
    expect(await screen.findByRole('heading', { name: 'Import is for admins' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load sample tracker' })).toBeNull();
  });

  it('lists recent imports with their outcome', async () => {
    renderApp('/import');
    const table = await screen.findByRole('table', { name: 'Recent imports' });
    expect(within(table).getByText('178 created · 2 skipped')).toBeInTheDocument();
    expect(
      within(table).getByText('The import stopped at row 31: the database was unavailable. Try again.'),
    ).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'partner-tracker-2025.xlsx' })).toHaveAttribute(
      'href',
      '/import?job=5',
    );
  });

  it('loads the sample tracker and opens column mapping with the guesses', async () => {
    server.use(http.post('*/api/imports/sample', () => HttpResponse.json(importJob(), { status: 201 })));
    serveJob(importJob(), importPreview({ status: 'uploaded' }));
    const { router } = renderApp('/import');

    await userEvent.click(await screen.findByRole('button', { name: 'Load sample tracker' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ job: 7 });
    });
    const table = await screen.findByRole('table', { name: 'Column mapping' });
    const row = within(table).getByRole('row', { name: /Trigger Terms Present/ });
    expect(within(row).getByText('N, Y, yes')).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: /Trigger terms/ })).toBeInTheDocument();
  });

  it('uploads an xlsx and shows why the server refused it', async () => {
    server.use(
      http.post('*/api/imports', () =>
        HttpResponse.json(
          {
            code: 'invalid_input',
            message: "This file isn't a readable .xlsx workbook.",
            details: {},
            fields: [{ loc: ['body', 'file'], message: "This file isn't a readable .xlsx workbook." }],
          },
          { status: 422 },
        ),
      ),
    );
    const { container } = renderApp('/import');
    await screen.findByRole('button', { name: 'Upload tracker (.xlsx)' });
    const input = container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement)) throw new Error('no file input');
    await userEvent.upload(input, new File(['not a workbook'], 'tracker.xlsx'));
    expect(await screen.findByText("This file isn't a readable .xlsx workbook.")).toBeInTheDocument();
  });
});

describe('Import: steps', () => {
  it('saves the column mapping and moves to the preview when nothing is unmapped', async () => {
    serveJob(importJob(), importPreview({ status: 'uploaded' }));
    server.use(
      http.put('*/api/imports/7/mapping', async ({ request }) => {
        mappings.push((await request.json()) as ImportMappingIn);
        return HttpResponse.json(importPreview());
      }),
    );
    const { router } = renderApp(`/import${searchString({ job: 7 })}`);
    await screen.findByRole('table', { name: 'Column mapping' });

    await userEvent.click(screen.getByRole('button', { name: /Imports as, Live URL/ }));
    await userEvent.click(await screen.findByRole('option', { name: "Don't import" }));
    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }));

    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ step: 'preview' });
    });
    const sent = mappings[0]?.columns ?? [];
    expect(sent).toHaveLength(17);
    expect(sent.find((c) => c.source === 'Live URL / Placement & Screenshot Link')?.target).toBe('ignore');
    expect(await screen.findByRole('heading', { name: 'Preview' })).toBeInTheDocument();
  });

  it('maps unmapped values, and puts a refused value on its own row', async () => {
    serveJob(
      importJob({ status: 'mapped' }),
      importPreview({
        unmapped: CUSTOM_UNMAPPED,
        problems: CUSTOM_PROBLEMS,
        rows: CUSTOM_ROWS,
        counts: CUSTOM_COUNTS,
      }),
    );
    server.use(
      http.put('*/api/imports/7/mapping', async ({ request }) => {
        mappings.push((await request.json()) as ImportMappingIn);
        return HttpResponse.json(
          {
            code: 'invalid_input',
            message: "'LendStack' isn't a valid Partner.",
            details: {},
            fields: [
              { loc: ['body', 'value_mappings', 0, 'value'], message: "'LendStack' isn't a valid Partner." },
            ],
          },
          { status: 422 },
        );
      }),
    );
    renderApp(`/import${searchString({ job: 7 })}`);

    const table = await screen.findByRole('table', { name: 'Values to map' });
    const status = within(table).getByRole('row', { name: /On Hold/ });
    expect(within(status).getByText('3 rows')).toBeInTheDocument();
    await userEvent.click(within(status).getByRole('button', { name: /Imports as/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'In review' }));
    const partner = within(table).getByRole('row', { name: /LendCompare Inc\./ });
    await userEvent.click(within(partner).getByRole('button', { name: /Imports as/ }));
    await userEvent.click(await screen.findByRole('option', { name: 'LendStack' }));

    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    expect(await within(partner).findByText("'LendStack' isn't a valid Partner.")).toBeInTheDocument();
    expect(mappings[0]).toEqual({
      status_values: [{ source_value: 'On Hold', status: 'in_review' }],
      value_mappings: [{ field: 'partner', source_value: 'LendCompare Inc.', value: 'LendStack' }],
    });
  });

  it('previews counts and problems grouped by severity, with row numbers', async () => {
    serveJob(
      importJob({ status: 'mapped' }),
      importPreview({ problems: CUSTOM_PROBLEMS, rows: CUSTOM_ROWS, counts: CUSTOM_COUNTS }),
    );
    renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);

    expect(await screen.findByRole('heading', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.getByText('35').closest('.app-import-count')).toHaveTextContent('Ready to import');
    expect(screen.getByText('Blocked by errors').closest('.app-import-count')?.textContent).toMatch(
      /errors\s*5$/,
    );
    expect(screen.getByRole('button', { name: /Warnings · 2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import 35 items' })).toBeInTheDocument();
    expect(screen.getByText(/5 rows with errors are skipped/)).toBeInTheDocument();
  });

  it('lists every blocked row, and says so when a row has more than one error', async () => {
    serveJob(
      importJob({ status: 'mapped' }),
      importPreview({ problems: CUSTOM_PROBLEMS, rows: CUSTOM_ROWS, counts: CUSTOM_COUNTS }),
    );
    renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);

    // 6 errors on 5 rows (row 31 has two): the header names both, and the rows listed are the 5 skipped.
    expect(await screen.findByRole('button', { name: /Errors · 6 in 5 rows/ })).toBeInTheDocument();
    const errors = screen.getByRole('table', { name: 'Errors' });
    const listed = within(errors)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getAllByRole('cell')[0]?.textContent);
    expect(new Set(listed)).toEqual(new Set(['12', '15', '18', '27', '31']));
    expect(new Set(listed).size).toBe(CUSTOM_COUNTS.blocked);
    expect(within(errors).getByRole('row', { name: /12.*Status.*On Hold/ })).toBeInTheDocument();
  });

  it('commits, shows progress while polling, then the summary with links to the imported items', async () => {
    let status: ImportJobOut['status'] = 'mapped';
    let polls = 0;
    serveJob(
      () => {
        if (status === 'committing') {
          polls += 1;
          if (polls >= 2) status = 'committed';
        }
        return importJob({
          status,
          summary: status === 'committed' ? { created: 178, skipped: 2, partners_created: 8 } : null,
        });
      },
      () => (status === 'committed' ? committedPreview() : importPreview()),
    );
    server.use(
      http.post('*/api/imports/7/commit', () => {
        status = 'committing';
        return HttpResponse.json(importJob({ status: 'committing' }), { status: 202 });
      }),
    );
    renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);

    await userEvent.click(await screen.findByRole('button', { name: 'Import 178 items' }));
    expect(await screen.findByText(/Importing 178 items/)).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'Imported 178 items' }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByText('8').closest('.app-import-count')).toHaveTextContent('Partners created');
    const items = await screen.findByRole('table', { name: 'Imported items' });
    expect(within(items).getByRole('link', { name: 'PL Credit Card Payoff postcard' })).toHaveAttribute(
      'href',
      '/items/400',
    );
    // Two of the created rows are approved: those are what the library's approved view adds.
    expect(screen.getByRole('link', { name: 'Approved legacy items (2)' })).toHaveAttribute(
      'href',
      '/library?legacy=only',
    );
  });

  it('lists what the import skipped and warned about, collapsed under the created items', async () => {
    serveJob(
      importJob({ status: 'committed', summary: { created: 5, skipped: 2, partners_created: 0 } }),
      () => committedPreview(),
    );
    renderApp(`/import${searchString({ job: 7 })}`);

    const skipped = await screen.findByRole('button', { name: 'Skipped (2)' });
    const warnings = screen.getByRole('button', { name: /^Warnings \(\d+\)$/ });
    expect(skipped).toHaveAttribute('aria-expanded', 'false');
    expect(warnings).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(skipped);
    const table = screen.getByRole('table', { name: 'Skipped rows' });
    expect(
      within(table).getByRole('row', { name: /68.*MCR-25-066.*Duplicate of an earlier row/ }),
    ).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: /19.*Not a tracker row/ })).toBeInTheDocument();
  });

  it('offers to map values from the preview while some are unmapped', async () => {
    serveJob(
      importJob({ status: 'mapped' }),
      importPreview({
        unmapped: CUSTOM_UNMAPPED,
        problems: CUSTOM_PROBLEMS,
        rows: CUSTOM_ROWS,
        counts: CUSTOM_COUNTS,
      }),
    );
    const { router } = renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Map 3 values' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ job: 7, step: 'values' });
    });
    expect(await screen.findByRole('table', { name: 'Values to map' })).toBeInTheDocument();
  });

  it('shows each problem row as imported or skipped, from the preview rows', async () => {
    serveJob(importJob({ status: 'mapped' }), importPreview());
    renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);
    await userEvent.click(await screen.findByRole('button', { name: /^Info · / }));
    const info = screen.getByRole('table', { name: 'Info' });
    expect(within(info).getByRole('row', { name: /^19 .*Skipped/ })).toBeInTheDocument();
  });

  it("shows the server's reason when commit is refused (409)", async () => {
    serveJob(importJob({ status: 'mapped' }), importPreview());
    server.use(
      http.post('*/api/imports/7/commit', () =>
        HttpResponse.json(
          { code: 'conflict', message: 'Map a column to Status before importing.' },
          { status: 409 },
        ),
      ),
    );
    renderApp(`/import${searchString({ job: 7, step: 'preview' })}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Import 178 items' }));
    expect(await screen.findByText('Map a column to Status before importing.')).toBeInTheDocument();
  });

  it('says why a commit failed and offers to try again', async () => {
    serveJob(
      importJob({
        status: 'failed',
        error: 'The import stopped at row 31: the database was unavailable. Try again.',
      }),
      importPreview({ status: 'failed' }),
    );
    renderApp(`/import${searchString({ job: 7 })}`);
    expect(
      await screen.findByText('The import stopped at row 31: the database was unavailable. Try again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try the import again' })).toBeInTheDocument();
  });
});
