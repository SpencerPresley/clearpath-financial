/*
 * The queue's URL contract. Filters, sort, layout, and the open preview item live in validated search params,
 * so any queue state is a link (decisions.md "Stack": filters live in validated URL search params).
 *
 * Every field is guarded with .catch(): a stale or hand-edited URL drops the bad field and still renders,
 * rather than throwing the route into its error boundary.
 */
import { z } from 'zod';

import { Channel, ItemSort, ItemStatus, Product, ReopenReason, RiskTier } from '../../api/generated/model';
import type { ItemFilter, ListItemsParams, SavedViewIn, SavedViewOut } from '../../api/generated/model';

function enumList<T extends string>(values: readonly T[]) {
  const allowed = new Set<string>(values);
  return z
    .array(z.unknown())
    .transform((list) => {
      const kept = list.filter((v): v is T => typeof v === 'string' && allowed.has(v));
      return kept.length > 0 ? kept : undefined;
    })
    .optional()
    .catch(undefined);
}

const idList = z
  .array(z.number().int().positive())
  .transform((list) => (list.length > 0 ? list : undefined))
  .optional()
  .catch(undefined);

const flag = z.boolean().optional().catch(undefined);

export const LAYOUTS = ['table', 'board'] as const;
export type QueueLayout = (typeof LAYOUTS)[number];

export const queueSearchSchema = z.object({
  /** Built-in view id or `saved:<id>`; the base the current filters are compared against. */
  view: z.string().max(40).optional().catch(undefined),
  q: z.string().max(200).optional().catch(undefined),
  status: enumList(Object.values(ItemStatus)),
  product: enumList(Object.values(Product)),
  channel: enumList(Object.values(Channel)),
  risk_tier: enumList(Object.values(RiskTier)),
  reopen_reason: enumList(Object.values(ReopenReason)),
  partner_id: idList,
  assignee_id: idList,
  mine: flag,
  unassigned: flag,
  has_open_findings: flag,
  /** Submitted more than N days ago. */
  waiting: z.number().int().min(0).max(3650).optional().catch(undefined),
  sort: z.enum(Object.values(ItemSort)).default('queue').catch('queue'),
  layout: z.enum(LAYOUTS).default('table').catch('table'),
  /** Item shown in the preview drawer. */
  item: z.number().int().positive().optional().catch(undefined),
});

export type QueueSearch = z.output<typeof queueSearchSchema>;

export const FILTER_KEYS = [
  'q',
  'status',
  'product',
  'channel',
  'risk_tier',
  'reopen_reason',
  'partner_id',
  'assignee_id',
  'mine',
  'unassigned',
  'has_open_findings',
  'waiting',
] as const satisfies readonly (keyof QueueSearch)[];

export type FilterKey = (typeof FILTER_KEYS)[number];
export type QueueFilters = Partial<Pick<QueueSearch, FilterKey>>;

export type BuiltInViewId = 'mine' | 'unassigned' | 'waiting' | 'rereview' | 'active';

export interface BuiltInView {
  id: BuiltInViewId;
  label: string;
  filters: QueueFilters;
}

export const BUILT_IN_VIEWS: readonly BuiltInView[] = [
  { id: 'mine', label: 'My queue', filters: { mine: true } },
  { id: 'unassigned', label: 'Unassigned', filters: { unassigned: true } },
  { id: 'waiting', label: 'Waiting >3 days', filters: { waiting: 3 } },
  {
    id: 'rereview',
    label: 'Needs re-review',
    // reopen_reason, not status=needs_rereview: a re-review the reviewer has opened is in_review but is still
    // a re-review of live content (and still ranks first in queue order).
    filters: { reopen_reason: ['terms_changed', 'approval_expired', 'drift_detected'] },
  },
  {
    id: 'active',
    label: 'All active',
    filters: { status: ['submitted', 'in_review', 'changes_requested', 'needs_rereview'] },
  },
];

const BASE: Pick<QueueSearch, 'sort' | 'layout'> = { sort: 'queue', layout: 'table' };

export function builtInView(id: string | undefined): BuiltInView | undefined {
  return BUILT_IN_VIEWS.find((v) => v.id === id);
}

/** The search a built-in view opens to (queue order, table layout). */
export function viewSearch(id: BuiltInViewId): QueueSearch {
  const view = builtInView(id);
  return { ...BASE, view: id, ...(view?.filters ?? {}) };
}

export function filtersOf(search: QueueFilters): QueueFilters {
  const out: Record<string, unknown> = {};
  for (const key of FILTER_KEYS) {
    const value = search[key];
    if (value === undefined || value === false) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    if (typeof value === 'string' && value.trim() === '') continue;
    out[key] = typeof value === 'string' ? value.trim() : value;
  }
  return out;
}

export function hasFilters(search: QueueFilters): boolean {
  return Object.keys(filtersOf(search)).length > 0;
}

function canonical(filters: QueueFilters): string {
  const f = filtersOf(filters) as Record<string, unknown>;
  const sorted = Object.keys(f)
    .sort()
    .map((key) => {
      const value = f[key];
      return [key, Array.isArray(value) ? [...(value as (string | number)[])].sort() : value];
    });
  return JSON.stringify(sorted);
}

/** Same filters, ignoring array order and absent-vs-empty/false. */
export function sameFilters(a: QueueFilters, b: QueueFilters): boolean {
  return canonical(a) === canonical(b);
}

/** Parse raw URL search. A URL with no filters and no view opens My queue (spec §4.3). */
export function parseQueueSearch(raw: Record<string, unknown>): QueueSearch {
  const search = queueSearchSchema.parse(raw);
  if (search.view === undefined && !hasFilters(search)) {
    return { ...search, ...viewSearch('mine'), layout: search.layout, item: search.item };
  }
  return search;
}

export function toListParams(
  search: QueueSearch,
  extra: { cursor?: string | null; limit?: number } = {},
): ListItemsParams {
  const f = filtersOf(search);
  const params: ListItemsParams = {};
  if (f.q !== undefined) params.q = f.q;
  if (f.status) params.status = f.status;
  if (f.product) params.product = f.product;
  if (f.channel) params.channel = f.channel;
  if (f.risk_tier) params.risk_tier = f.risk_tier;
  if (f.reopen_reason) params.reopen_reason = f.reopen_reason;
  if (f.partner_id) params.partner_id = f.partner_id;
  if (f.assignee_id) params.assignee_id = f.assignee_id;
  if (f.mine) params.mine = true;
  if (f.unassigned) params.unassigned = true;
  if (f.has_open_findings !== undefined) params.has_open_findings = f.has_open_findings;
  if (f.waiting !== undefined) params.waiting_more_than_days = f.waiting;
  params.sort = search.sort;
  if (extra.cursor !== undefined && extra.cursor !== null) params.cursor = extra.cursor;
  if (extra.limit !== undefined) params.limit = extra.limit;
  return params;
}

// ---- Saved views (persisted through /views) ------------------------------------------------------------

export const SAVED_PREFIX = 'saved:';

export function savedViewKey(id: number): string {
  return `${SAVED_PREFIX}${String(id)}`;
}

function filterFromItemFilter(f: ItemFilter): QueueFilters {
  return queueSearchSchema.partial().parse({
    q: f.q ?? undefined,
    status: f.status,
    product: f.product,
    channel: f.channel,
    risk_tier: f.risk_tier,
    reopen_reason: f.reopen_reason,
    partner_id: f.partner_id,
    assignee_id: f.assignee_id,
    mine: f.mine,
    unassigned: f.unassigned,
    has_open_findings: f.has_open_findings ?? undefined,
    waiting: f.waiting_more_than_days ?? undefined,
  });
}

export function savedViewToSearch(view: SavedViewOut): QueueSearch {
  return {
    ...BASE,
    ...filtersOf(filterFromItemFilter(view.filters)),
    view: savedViewKey(view.id),
    sort: view.sort ?? 'queue',
  };
}

export function searchToSavedViewIn(
  name: string,
  search: QueueSearch,
  columns: readonly string[],
): SavedViewIn {
  const { waiting, ...rest } = filtersOf(search);
  const filters: ItemFilter = { ...rest };
  if (waiting !== undefined) filters.waiting_more_than_days = waiting;
  return { name, filters, sort: search.sort, columns: [...columns] };
}

export type ActiveView =
  | { kind: 'builtin'; id: BuiltInViewId; label: string; modified: boolean; base: QueueSearch }
  | { kind: 'saved'; id: number; label: string; modified: boolean; base: QueueSearch; view: SavedViewOut }
  | { kind: 'custom'; label: string; modified: false };

/** Which view the current URL is, and whether its filters or sort have moved away from it. */
export function activeView(search: QueueSearch, saved: readonly SavedViewOut[]): ActiveView {
  if (search.view?.startsWith(SAVED_PREFIX) === true) {
    const id = Number(search.view.slice(SAVED_PREFIX.length));
    const view = saved.find((v) => v.id === id);
    if (view !== undefined) {
      const base = savedViewToSearch(view);
      const modified = !sameFilters(search, base) || search.sort !== base.sort;
      return { kind: 'saved', id, label: view.name, modified, base, view };
    }
  }
  const named = builtInView(search.view);
  if (named !== undefined) {
    const base = viewSearch(named.id);
    const modified = !sameFilters(search, named.filters) || search.sort !== 'queue';
    return { kind: 'builtin', id: named.id, label: named.label, modified, base };
  }
  const matched = BUILT_IN_VIEWS.find((v) => sameFilters(search, v.filters));
  if (matched !== undefined) {
    const base = viewSearch(matched.id);
    return { kind: 'builtin', id: matched.id, label: matched.label, modified: search.sort !== 'queue', base };
  }
  return { kind: 'custom', label: 'Custom filters', modified: false };
}
