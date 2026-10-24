/*
 * API stand-in for the Library and Import e2e flows and their UI-review screenshots. Serves the fixtures in
 * src/test/fixtures/{library,imports}.ts and keeps just enough state for a flow to run end to end: export and
 * evidence-pack jobs become ready after a poll, and an import moves uploaded → mapped → committing → committed.
 */
import type { Page, Route } from '@playwright/test';

import type {
  ImportJobOut,
  ImportMappingIn,
  ImportPreviewOut,
  ItemRowOut,
  MeOut,
  SearchHitOut,
} from '../src/api/generated/model';
import { committedPreview, importJob, importPreview, recentImports } from '../src/test/fixtures/imports';
import {
  APPROVED_ROWS,
  exportJob,
  LIBRARY_PARTNERS,
  ME_ADMIN,
  PRECEDENT_HITS,
  searchResults,
} from '../src/test/fixtures/library';

type Behavior = 'hang' | number;

export interface LibraryStubOptions {
  me?: MeOut;
  /** Approved rows; or 'hang' (loading) / a status code (error). */
  library?: ItemRowOut[] | Behavior;
  /** A second page of approved rows (the first page then has a next_cursor). */
  morePages?: ItemRowOut[] | Behavior;
  hits?: SearchHitOut[] | Behavior;
  /** Export job: 'running' stays running; 'failed' fails; default becomes ready on the second poll. */
  exportOutcome?: 'ready' | 'running' | 'failed';
  /** Evidence-pack POST answers 409 for these item ids. */
  packRefused?: number[];
  /** Import job to serve at /api/imports/7 (and its preview). */
  job?: ImportJobOut;
  preview?: ImportPreviewOut;
  recent?: ReturnType<typeof recentImports> | Behavior;
  /** How many job polls a commit stays committing for. */
  commitPolls?: number;
}

export interface LibraryStubState {
  posted: { method: string; path: string; body: unknown }[];
}

const XLSX_BYTES = Buffer.from('PK\u0003\u0004 stub workbook');

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function refuse(route: Route, status: number, message: string) {
  return json(route, { code: status === 409 ? 'conflict' : 'server_error', message }, status);
}

export async function stubLibraryApi(
  page: Page,
  options: LibraryStubOptions = {},
): Promise<LibraryStubState> {
  const state: LibraryStubState = { posted: [] };
  let exportPolls = 0;
  let job: ImportJobOut | undefined = options.job;
  let preview: ImportPreviewOut =
    options.preview ?? importPreview({ status: options.job?.status ?? 'uploaded' });
  let commitPolls = 0;

  await page.route(/\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = request.method();
    const isJson = (request.headers()['content-type'] ?? '').includes('application/json');
    const body: unknown = method !== 'GET' && isJson ? request.postDataJSON() : undefined;
    if (method !== 'GET') state.posted.push({ method, path, body });
    let m: RegExpExecArray | null;

    if (path === '/health') return json(route, { status: 'ok', database: true });
    if (path === '/me') return json(route, options.me ?? ME_ADMIN);
    if (path === '/partners') return json(route, LIBRARY_PARTNERS);

    // ---- library ----
    if (path === '/library') {
      const lib = options.library ?? APPROVED_ROWS;
      if (lib === 'hang') return;
      if (typeof lib === 'number')
        return refuse(route, lib, 'The library is temporarily unavailable. Try again in a minute.');
      if (url.searchParams.get('cursor') === 'page-2') {
        const more = options.morePages ?? [];
        if (more === 'hang') return;
        if (typeof more === 'number') return refuse(route, more, "Couldn't load more items. Try again.");
        return json(route, { rows: more, next_cursor: null });
      }
      return json(route, { rows: lib, next_cursor: options.morePages === undefined ? null : 'page-2' });
    }
    if (path === '/library/search') {
      const hits = options.hits ?? PRECEDENT_HITS;
      if (hits === 'hang') return;
      if (typeof hits === 'number')
        return refuse(route, hits, 'Search is unavailable right now. Try again in a minute.');
      const mode = url.searchParams.get('mode') === 'text' ? 'text' : 'phrase';
      return json(route, searchResults(hits, url.searchParams.get('query') ?? '', mode));
    }

    // ---- exports and evidence packs ----
    if (path === '/exports' && method === 'POST') return json(route, exportJob({ id: 9 }), 202);
    if ((m = /^\/items\/(\d+)\/evidence-pack$/.exec(path)) && method === 'POST') {
      const id = Number(m[1]);
      if ((options.packRefused ?? []).includes(id)) {
        return refuse(route, 409, `CP-${String(id)} has no approval yet; an evidence pack records one.`);
      }
      return json(route, exportJob({ id: 30 + (id % 10), kind: 'evidence_pack', item_id: id }), 202);
    }
    if ((m = /^\/exports\/(\d+)$/.exec(path))) {
      const id = Number(m[1]);
      if (id === 9) {
        exportPolls += 1;
        const outcome = options.exportOutcome ?? 'ready';
        if (outcome === 'running' || exportPolls < 2)
          return json(route, exportJob({ id, status: 'running' }));
        if (outcome === 'failed') {
          return json(
            route,
            exportJob({ id, status: 'failed', error: 'The export ran out of time. Try a narrower view.' }),
          );
        }
        return json(
          route,
          exportJob({
            id,
            status: 'ready',
            item_count: APPROVED_ROWS.length,
            filename: 'clearpath-export-2026-10-24.xlsx',
            download_url: '/api/exports/9/download',
          }),
        );
      }
      return json(
        route,
        exportJob({
          id,
          kind: 'evidence_pack',
          status: 'ready',
          item_count: 1,
          filename: 'CP-1088-evidence-pack-2026-10-24.zip',
          download_url: `/api/exports/${String(id)}/download`,
        }),
      );
    }
    if (/^\/exports\/\d+\/download$/.test(path)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers: { 'content-disposition': 'attachment; filename="clearpath-export-2026-10-24.xlsx"' },
        body: XLSX_BYTES,
      });
    }

    // ---- imports ----
    if (path === '/imports' && method === 'GET') {
      const recent = options.recent ?? recentImports();
      if (recent === 'hang') return;
      if (typeof recent === 'number') return refuse(route, recent, "Couldn't load recent imports.");
      return json(route, recent);
    }
    if ((path === '/imports' || path === '/imports/sample') && method === 'POST') {
      job = importJob({
        filename: path === '/imports/sample' ? 'clearpath_review_tracker.xlsx' : 'tracker.xlsx',
      });
      preview = importPreview({ status: 'uploaded' });
      return json(route, job, 201);
    }
    if ((m = /^\/imports\/7(\/[a-z]+)?$/.exec(path))) {
      if (job === undefined) return refuse(route, 404, 'Import 7 not found.');
      const sub = m[1] as string | undefined; // the optional group is undefined when absent
      if (sub === undefined) {
        if (job.status === 'committing') {
          commitPolls += 1;
          if (commitPolls >= (options.commitPolls ?? 2)) {
            job = {
              ...job,
              status: 'committed',
              committed_at: '2026-10-24T15:01:00Z',
              summary: { created: 178, skipped: 2, partners_created: 8 },
            };
            preview = committedPreview();
          }
        }
        return json(route, job);
      }
      if (sub === '/preview') return json(route, preview);
      if (sub === '/mapping' && method === 'PUT') {
        const data = body as ImportMappingIn;
        job = {
          ...job,
          status: 'mapped',
          updated_at: new Date().toISOString(),
          columns: job.columns.map((c) => ({
            ...c,
            field: data.columns?.find((x) => x.source === c.name)?.target ?? c.field,
          })),
        };
        preview = { ...preview, status: 'mapped', unmapped: [] };
        return json(route, preview);
      }
      if (sub === '/commit' && method === 'POST') {
        job = { ...job, status: 'committing', commit_requested_at: new Date().toISOString() };
        return json(route, job, 202);
      }
    }
    return json(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
  return state;
}
