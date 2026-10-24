/*
 * API stubs for the Offer terms and Partners e2e flows and UI-review screenshots. Serves the fixtures in
 * src/test/fixtures/termsPartners.ts; a publish swaps the current personal loan terms for v13, as the backend
 * would. Each option takes data, an HTTP status to fail with, or 'hang' to hold the loading state.
 */
import type { Page, Route } from '@playwright/test';

import type {
  ImpactPreviewOut,
  ItemRowOut,
  MeOut,
  OfferTermsOut,
  PartnerDetailOut,
  PartnerFindingOut,
  PartnerRowOut,
} from '../src/api/generated/model';
import {
  CC_HISTORY,
  CURRENT_TERMS,
  IMPACT_PL,
  LEAD_ME,
  PARTNER_DETAIL,
  PARTNER_FINDINGS_PAGE_1,
  PARTNER_FINDINGS_PAGE_2,
  PARTNER_ROWS,
  partnerItemRows,
  PL_HISTORY,
  PL_V13,
} from '../src/test/fixtures/termsPartners';

type Stub<T> = T | number | 'hang';

export interface TermsPartnersStub {
  me?: MeOut;
  current?: Stub<OfferTermsOut[]>;
  history?: Stub<OfferTermsOut[]>;
  preview?: Stub<ImpactPreviewOut>;
  /** Delay before each preview answers, to capture the checking state. */
  previewDelayMs?: number;
  partners?: Stub<PartnerRowOut[]>;
  partner?: Stub<PartnerDetailOut>;
  items?: Stub<ItemRowOut[]>;
  findings?: Stub<PartnerFindingOut[]>;
  /** Another lead published this first: the first publish is a 409 and the current terms become it. */
  publishConflict?: OfferTermsOut;
}

export interface Posted {
  method: string;
  path: string;
  body: unknown;
}

function fulfill(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function failure(route: Route, status: number, what: string) {
  return fulfill(
    route,
    status === 404
      ? { code: 'not_found', message: `${what} doesn't exist.` }
      : status === 403
        ? { code: 'not_permitted', message: `${what} are for reviewers and leads.` }
        : { code: 'server_error', message: `${what} are unavailable right now. Try again in a minute.` },
    status,
  );
}

/** Answers a stubbed value: data, a failure status, or never. */
async function serve<T>(route: Route, stub: Stub<T> | undefined, what: string, fallback: T): Promise<void> {
  if (stub === 'hang') return;
  if (typeof stub === 'number') return failure(route, stub, what);
  return fulfill(route, stub ?? fallback);
}

export async function stubTermsPartners(page: Page, opts: TermsPartnersStub = {}): Promise<Posted[]> {
  const posted: Posted[] = [];
  let current = opts.current;
  let conflict = opts.publishConflict;
  let preview = opts.preview;
  await page.route(/\/(api|_allauth)\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    if (method !== 'GET') {
      let body: unknown = request.postData();
      try {
        body = request.postDataJSON() as unknown;
      } catch {
        // multipart (uploads): keep the raw body
      }
      posted.push({ method, path, body });
    }

    if (path === '/api/health') return fulfill(route, { status: 'ok', database: true });
    if (path === '/api/me') return fulfill(route, opts.me ?? LEAD_ME);
    if (path.startsWith('/_allauth/')) return fulfill(route, { status: 401 }, 401);

    if (path === '/api/terms/current') return serve(route, current, 'Offer terms', CURRENT_TERMS);
    if (path === '/api/terms/impact-preview') {
      if (opts.previewDelayMs !== undefined) await new Promise((r) => setTimeout(r, opts.previewDelayMs));
      return serve(route, preview, 'Impact previews', IMPACT_PL);
    }
    if (path === '/api/terms' && method === 'POST') {
      if (conflict !== undefined) {
        current = [conflict, ...CURRENT_TERMS.slice(1)];
        const version = conflict.version;
        preview ??= {
          ...IMPACT_PL,
          summary: IMPACT_PL.summary.replace('v12', `v${String(version)}`),
          current_version: version,
          next_version: version + 1,
        };
        conflict = undefined;
        return fulfill(
          route,
          {
            code: 'conflict',
            message: `The offer terms changed since you opened this (v${String(version)} is in effect now). Review the impact again.`,
          },
          409,
        );
      }
      current = [PL_V13, ...CURRENT_TERMS.slice(1)];
      return fulfill(route, PL_V13, 201);
    }
    if (path === '/api/terms') {
      const fallback = url.searchParams.get('product') === 'credit_card' ? CC_HISTORY : PL_HISTORY;
      return serve(route, opts.history, 'Versions', fallback);
    }

    if (path === '/api/partners' && method === 'POST') {
      return fulfill(route, { ...PARTNER_DETAIL, id: 40, name: 'FundFlow' }, 201);
    }
    if (path === '/api/partners') {
      if (opts.partners !== undefined) return serve(route, opts.partners, 'Partners', PARTNER_ROWS);
      const status = url.searchParams.get('status');
      const q = url.searchParams.get('q')?.toLowerCase();
      return fulfill(
        route,
        PARTNER_ROWS.filter(
          (p) =>
            (status === null || p.status === status) && (q === undefined || p.name.toLowerCase().includes(q)),
        ),
      );
    }
    if (/^\/api\/partners\/\d+\/findings$/.test(path)) {
      if (opts.findings !== undefined) {
        if (opts.findings === 'hang' || typeof opts.findings === 'number') {
          return serve(route, opts.findings, 'Findings', []);
        }
        return fulfill(route, { rows: opts.findings, next_cursor: null });
      }
      const rule = url.searchParams.get('rule_id');
      if (rule !== null) {
        const rows = [...PARTNER_FINDINGS_PAGE_1, ...PARTNER_FINDINGS_PAGE_2].filter(
          (f) => f.rule_id === rule,
        );
        return fulfill(route, { rows, next_cursor: null });
      }
      return url.searchParams.get('cursor') === 'page-2'
        ? fulfill(route, { rows: PARTNER_FINDINGS_PAGE_2, next_cursor: null })
        : fulfill(route, { rows: PARTNER_FINDINGS_PAGE_1, next_cursor: 'page-2' });
    }
    const partner = /^\/api\/partners\/(\d+)$/.exec(path);
    if (partner) {
      const id = Number(partner[1]);
      if (opts.partner === undefined && id !== PARTNER_DETAIL.id && id !== 40) {
        return failure(route, 404, `Partner ${String(id)}`);
      }
      const base = id === 40 ? { ...PARTNER_DETAIL, id: 40, name: 'FundFlow' } : PARTNER_DETAIL;
      return serve(route, opts.partner, 'Partners', base);
    }
    if (path === '/api/items') {
      if (opts.items === 'hang' || typeof opts.items === 'number')
        return serve(route, opts.items, 'Items', []);
      const rows = opts.items ?? partnerItemRows();
      return fulfill(route, { rows, next_cursor: null, total: rows.length });
    }
    return fulfill(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
  return posted;
}
