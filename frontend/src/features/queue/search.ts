/*
 * The queue's URL contract. Filters, sort, layout, and the open preview item live in validated search params,
 * so any queue state is a link (decisions.md "Stack": filters live in validated URL search params).
 *
 * Every field is guarded with .catch(): a stale or hand-edited URL drops the bad field and still renders,
 * rather than throwing the route into its error boundary.
 */
import { z } from 'zod';

import { Channel, ItemSort, ItemStatus, Product, ReopenReason, RiskTier } from '../../api/generated/model';
import type {
  ItemFilter,
  ListItemsParams,
  QueueStatFiltersOut,
  SavedViewIn,
  SavedViewOut,
} from '../../api/generated/model';

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
  /** Tri-state: false is a real filter (no legacy imports), unlike mine/unassigned where false means "any". */
  is_legacy: flag,
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
  'is_legacy',
  'waiting',
] as const satisfies readonly (keyof QueueSearch)[];

/** Keys where `false` narrows the result (so it is kept, not dropped as "no constraint"). */
const TRI_STATE_KEYS: ReadonlySet<FilterKey> = new Set(['has_open_findings', 'is_legacy']);

export type FilterKey = (typeof FILTER_KEYS)[number];
export type QueueFilters = Partial<Pick<QueueSearch, FilterKey>>;

export type BuiltInViewId = 'mine' | 'unassigned' | 'waiting' | 'rereview' | 'queue' | 'active';

export interface BuiltInView {
  id: BuiltInViewId;
  label: string;
  filters: QueueFilters;
  /** False: no tab in the view row (opened from its stat); 1280px fits five tabs plus Modified/Save view. */
  tab?: false;
}

/** The review queue's statuses (backend reviews.models.QUEUE_STATUSES). */
const QUEUED: ItemStatus[] = ['submitted', 'in_review', 'needs_rereview'];

/*
 * Each view that has a stat is that stat's filter, exactly (GET /items/stats `filters`; the ledger ruling that a
 * number must equal the list it links to). Every one names its statuses and leaves out legacy imports, so the
 * set is the same under any sort; search.test.ts checks them against the server's definitions.
 */
export const BUILT_IN_VIEWS: readonly BuiltInView[] = [
  { id: 'mine', label: 'My queue', filters: { status: QUEUED, is_legacy: false, mine: true } },
  { id: 'unassigned', label: 'Unassigned', filters: { status: QUEUED, is_legacy: false, unassigned: true } },
  { id: 'waiting', label: 'Waiting >3 days', filters: { status: QUEUED, is_legacy: false, waiting: 3 } },
  // By status: a re-review a reviewer has opened is in review, and counts in My queue instead.
  { id: 'rereview', label: 'Needs re-review', filters: { status: ['needs_rereview'], is_legacy: false } },
  { id: 'queue', label: 'In queue', filters: { status: QUEUED, is_legacy: false }, tab: false },
  {
    id: 'active',
    label: 'All active',
    filters: { status: ['submitted', 'in_review', 'changes_requested', 'needs_rereview'], is_legacy: false },
  },
];

/** Which built-in view each queue stat is the total of. */
export const STAT_VIEWS = {
  open: 'queue',
  mine: 'mine',
  unassigned: 'unassigned',
  waiting_over_3_days: 'waiting',
  needs_rereview: 'rereview',
} as const satisfies Record<keyof QueueStatFiltersOut, BuiltInViewId>;

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
    if (value === undefined || (value === false && !TRI_STATE_KEYS.has(key))) continue;
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

function normalize(search: QueueSearch): QueueSearch {
  if (search.view === undefined && !hasFilters(search)) {
    return { ...search, ...viewSearch('mine'), layout: search.layout, item: search.item };
  }
  return search;
}

/**
 * The route's search schema: the field guards plus the default view. A URL with no filters and no view opens
 * My queue (spec §4.3). As a schema (not a function) the router types link input as the all-optional input.
 */
export const queueRouteSearchSchema = queueSearchSchema.transform(normalize);

export function parseQueueSearch(raw: Record<string, unknown>): QueueSearch {
  return queueRouteSearchSchema.parse(raw);
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
  if (f.is_legacy !== undefined) params.is_legacy = f.is_legacy;
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

/** The queue filters an API ItemFilter expresses (fields the queue has no control for are dropped). */
export function filtersFromItemFilter(f: ItemFilter): QueueFilters {
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
    is_legacy: f.is_legacy ?? undefined,
    waiting: f.waiting_more_than_days ?? undefined,
  });
}

/**
 * The search a stat opens: its built-in view, with the filters the server counted it with (so the list's
 * total is the number that was clicked, even if a client definition ever drifts; it would show as Modified).
 */
export function statSearch(stat: keyof QueueStatFiltersOut, filters: ItemFilter): QueueSearch {
  return { ...BASE, view: STAT_VIEWS[stat], ...filtersOf(filtersFromItemFilter(filters)) };
}

export function savedViewToSearch(view: SavedViewOut): QueueSearch {
  return {
    ...BASE,
    ...filtersOf(filtersFromItemFilter(view.filters)),
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
