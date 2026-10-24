/*
 * The library's URL contract: which view, the precedent query and mode, and the filters both views share. Every
 * field is .catch()-guarded (ui/search/params.ts), so a stale link still opens.
 *
 * Two views (ledger ruling): "Approved to run" is what may run now (GET /library, scope approved_to_run);
 * "Precedents" searches every version that ever received an approval (GET /library/search), with the item's
 * current status shown beside it: precedent value doesn't lapse, run-permission does.
 */
import { z } from 'zod';

import { Channel, Product } from '../../api/generated/model';
import type { ExportIn, ItemFilter, ListLibraryParams, SearchLibraryParams } from '../../api/generated/model';
import { enumList, idList, isoDate, nextDay, text } from '../../ui/search/params';

export const LIBRARY_TABS = ['approved', 'precedents'] as const;
export type LibraryTab = (typeof LIBRARY_TABS)[number];

export const SEARCH_MODES = ['phrase', 'text'] as const;
export type SearchModeId = (typeof SEARCH_MODES)[number];

export const LEGACY_CHOICES = ['include', 'exclude', 'only'] as const;
export type LegacyChoice = (typeof LEGACY_CHOICES)[number];

export const PAGE_SIZE = 50;
/** Precedent search returns the top hits only (the endpoint has no cursor; its cap is 100). */
export const SEARCH_LIMIT = 50;

export const librarySearchSchema = z.object({
  tab: z.enum(LIBRARY_TABS).default('approved').catch('approved'),
  /** Approved view: title or item key. */
  q: text(200),
  /** Precedents view: the wording to look for. */
  query: text(500),
  mode: z.enum(SEARCH_MODES).default('phrase').catch('phrase'),
  product: enumList(Object.values(Product)),
  channel: enumList(Object.values(Channel)),
  partner_id: idList,
  approved_from: isoDate,
  approved_to: isoDate,
  run_from: isoDate,
  run_to: isoDate,
  legacy: z.enum(LEGACY_CHOICES).default('include').catch('include'),
});

export type LibrarySearch = z.output<typeof librarySearchSchema>;

/** Defaults the router strips from links, so the plain /library URL is the default view. */
export const LIBRARY_DEFAULTS = { tab: 'approved', mode: 'phrase', legacy: 'include' } as const;

const FILTER_KEYS = [
  'product',
  'channel',
  'partner_id',
  'approved_from',
  'approved_to',
  'run_from',
  'run_to',
] as const satisfies readonly (keyof LibrarySearch)[];

export type LibraryFilterPatch = Partial<Pick<LibrarySearch, (typeof FILTER_KEYS)[number] | 'legacy' | 'q'>>;

/** The filters with nothing set: what "Clear filters" writes. */
export const CLEARED: LibraryFilterPatch = {
  product: undefined,
  channel: undefined,
  partner_id: undefined,
  approved_from: undefined,
  approved_to: undefined,
  run_from: undefined,
  run_to: undefined,
  legacy: 'include',
  q: undefined,
};

export function hasFilters(search: LibrarySearch): boolean {
  if (search.legacy !== 'include') return true;
  if (search.tab === 'approved' && search.q !== undefined) return true;
  return FILTER_KEYS.some((key) => search[key] !== undefined);
}

/** The shared filters as the API's ItemFilter. Approved dates are calendar days in UTC: [from, to + 1 day). */
export function toItemFilter(search: LibrarySearch): ItemFilter {
  const filter: ItemFilter = {};
  if (search.product) filter.product = search.product;
  if (search.channel) filter.channel = search.channel;
  if (search.partner_id) filter.partner_id = search.partner_id;
  if (search.approved_from) filter.approved_after = `${search.approved_from}T00:00:00Z`;
  if (search.approved_to) filter.approved_before = `${nextDay(search.approved_to)}T00:00:00Z`;
  if (search.run_from) filter.run_from = search.run_from;
  if (search.run_to) filter.run_to = search.run_to;
  if (search.legacy === 'exclude') filter.is_legacy = false;
  if (search.legacy === 'only') filter.is_legacy = true;
  return filter;
}

function approvedFilter(search: LibrarySearch): ItemFilter {
  const filter = toItemFilter(search);
  if (search.q !== undefined) filter.q = search.q.trim();
  return filter;
}

export function toListParams(search: LibrarySearch, cursor?: string | null): ListLibraryParams {
  const params: ListLibraryParams = { scope: 'approved_to_run', sort: 'updated', limit: PAGE_SIZE };
  if (cursor !== undefined && cursor !== null) params.cursor = cursor;
  return { ...params, ...approvedFilter(search) };
}

export function toSearchParams(search: LibrarySearch): SearchLibraryParams {
  return {
    query: (search.query ?? '').trim(),
    mode: search.mode,
    limit: SEARCH_LIMIT,
    ...toItemFilter(search),
  };
}

/**
 * POST /exports for the approved view. The export endpoint has no library scope, and only the queue sort carries
 * implicit statuses, so the view's "currently approved" is sent as an explicit status filter.
 */
export function exportBody(search: LibrarySearch, includeEvidencePacks: boolean): ExportIn {
  return {
    filters: { ...approvedFilter(search), status: ['approved'] },
    sort: 'updated',
    include_evidence_packs: includeEvidencePacks,
  };
}
