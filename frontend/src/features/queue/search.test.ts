import { describe, expect, it } from 'vitest';

import type { SavedViewOut } from '../../api/generated/model';
import { DEFAULT_TRAIL } from '../../ui/queueTrail';
import { STAT_FILTERS } from './fixtures';
import {
  BUILT_IN_VIEWS,
  STAT_VIEWS,
  activeView,
  builtInView,
  filtersFromItemFilter,
  filtersOf,
  parseQueueSearch,
  sameFilters,
  savedViewToSearch,
  searchToSavedViewIn,
  statSearch,
  toListParams,
  viewSearch,
} from './search';
import type { BuiltInViewId } from './search';

function savedView(overrides: Partial<SavedViewOut> = {}): SavedViewOut {
  return {
    id: 4,
    name: 'High-risk CA',
    created_at: '2026-10-20T10:00:00Z',
    filters: { risk_tier: ['high'], status: ['submitted', 'in_review'] },
    sort: 'oldest',
    columns: ['key', 'title', 'status'],
    ...overrides,
  };
}

describe('parseQueueSearch', () => {
  it('opens to My queue when the URL carries no filters', () => {
    const search = parseQueueSearch({});
    expect(search.view).toBe('mine');
    expect(search.mine).toBe(true);
    expect(search.status).toEqual(['submitted', 'in_review', 'needs_rereview']);
    expect(search.is_legacy).toBe(false);
    expect(search.sort).toBe('queue');
    expect(search.layout).toBe('table');
  });

  it('keeps is_legacy false (a real filter), and drops a non-boolean', () => {
    expect(parseQueueSearch({ view: 'x', is_legacy: false }).is_legacy).toBe(false);
    expect(parseQueueSearch({ view: 'x', is_legacy: 'no' }).is_legacy).toBeUndefined();
  });

  it('keeps an explicit view without adding My queue filters', () => {
    const search = parseQueueSearch({ view: 'active', status: ['submitted'] });
    expect(search.mine).toBeUndefined();
    expect(search.status).toEqual(['submitted']);
  });

  it('drops invalid fields instead of throwing', () => {
    const search = parseQueueSearch({
      view: 'active',
      status: ['bogus', 'in_review'],
      product: ['nope'],
      risk_tier: 7,
      item: 'x',
      sort: 'by-vibes',
      layout: 'kanban',
      waiting: -2,
      partner_id: ['a'],
      mine: 'yes',
    });
    expect(search.status).toEqual(['in_review']);
    expect(search.product).toBeUndefined();
    expect(search.risk_tier).toBeUndefined();
    expect(search.item).toBeUndefined();
    expect(search.sort).toBe('queue');
    expect(search.layout).toBe('table');
    expect(search.waiting).toBeUndefined();
    expect(search.partner_id).toBeUndefined();
    expect(search.mine).toBeUndefined();
  });

  it('keeps the drawer item and board layout', () => {
    const search = parseQueueSearch({ view: 'unassigned', unassigned: true, item: 12, layout: 'board' });
    expect(search.item).toBe(12);
    expect(search.layout).toBe('board');
  });
});

describe('toListParams', () => {
  it('maps queue filters to the API, omitting empty and false values', () => {
    const params = toListParams(
      parseQueueSearch({
        view: 'x',
        waiting: 3,
        status: [],
        unassigned: false,
        risk_tier: ['high'],
        q: '  ',
        sort: 'oldest',
      }),
    );
    expect(params).toEqual({ waiting_more_than_days: 3, risk_tier: ['high'], sort: 'oldest' });
  });

  it('passes cursor and limit through', () => {
    const params = toListParams(parseQueueSearch({ view: 'x', mine: true }), { cursor: 'abc', limit: 25 });
    expect(params).toEqual({ mine: true, sort: 'queue', cursor: 'abc', limit: 25 });
  });

  it('sends has_open_findings=false (the "No open findings" choice) instead of dropping it', () => {
    const params = toListParams(parseQueueSearch({ view: 'x', has_open_findings: false }));
    expect(params).toEqual({ has_open_findings: false, sort: 'queue' });
  });

  it('sends is_legacy=false, which a queue view needs to exclude legacy imports under any sort', () => {
    expect(toListParams({ ...viewSearch('mine'), sort: 'title' })).toEqual({
      status: ['submitted', 'in_review', 'needs_rereview'],
      is_legacy: false,
      mine: true,
      sort: 'title',
    });
  });

  it('never sends UI-only keys (view, layout, item)', () => {
    const params = toListParams(parseQueueSearch({ view: 'mine', mine: true, layout: 'board', item: 3 }));
    expect(Object.keys(params).sort()).toEqual(['mine', 'sort']);
  });
});

describe('views', () => {
  it('defines the six built-in views in order', () => {
    expect(BUILT_IN_VIEWS.map((v) => v.label)).toEqual([
      'My queue',
      'Unassigned',
      'Waiting >3 days',
      'Needs re-review',
      'In queue',
      'All active',
    ]);
  });

  it('is exactly the view each stat counts, as the server defines it', () => {
    // Stat number = the view's total only if the view sends the server's filter (ledger ruling).
    for (const [stat, id] of Object.entries(STAT_VIEWS) as [keyof typeof STAT_FILTERS, BuiltInViewId][]) {
      const fromServer = filtersFromItemFilter(STAT_FILTERS[stat]);
      expect(sameFilters(fromServer, builtInView(id)?.filters ?? {}), `${stat} -> ${id}`).toBe(true);
      expect(activeView(statSearch(stat, STAT_FILTERS[stat]), []), stat).toMatchObject({
        kind: 'builtin',
        id,
        modified: false,
      });
    }
  });

  it('counts Needs re-review by status, so the view matches its stat', () => {
    const rereview = BUILT_IN_VIEWS.find((v) => v.id === 'rereview');
    expect(rereview?.filters).toEqual({ status: ['needs_rereview'], is_legacy: false });
  });

  it('includes changes requested in All active, still without legacy imports', () => {
    const active = BUILT_IN_VIEWS.find((v) => v.id === 'active');
    expect(active?.filters.status).toEqual(['submitted', 'in_review', 'changes_requested', 'needs_rereview']);
    expect(active?.filters.is_legacy).toBe(false);
  });

  it('compares filters regardless of array order and absent-vs-empty', () => {
    expect(sameFilters({ status: ['in_review', 'submitted'] }, { status: ['submitted', 'in_review'] })).toBe(
      true,
    );
    expect(sameFilters({ status: [], mine: false, q: '' }, {})).toBe(true);
    expect(sameFilters({ mine: true }, { unassigned: true })).toBe(false);
  });

  it('finds the active built-in view and marks it modified when a filter is added', () => {
    const plain = activeView(viewSearch('unassigned'), []);
    expect(plain).toMatchObject({ kind: 'builtin', id: 'unassigned', label: 'Unassigned', modified: false });

    const narrowed = activeView({ ...viewSearch('unassigned'), risk_tier: ['high'] }, []);
    expect(narrowed).toMatchObject({ kind: 'builtin', id: 'unassigned', modified: true });
  });

  it('recognises a built-in view by its filters when the view key is missing', () => {
    const search = parseQueueSearch({
      unassigned: true,
      status: ['needs_rereview', 'submitted', 'in_review'],
      is_legacy: false,
    });
    expect(activeView(search, [])).toMatchObject({ kind: 'builtin', id: 'unassigned', modified: false });
  });

  it('reports a custom filter set that matches no view', () => {
    const search = parseQueueSearch({ product: ['credit_card'] });
    expect(activeView(search, [])).toMatchObject({ kind: 'custom', modified: false });
  });

  it('resolves a saved view and detects a changed sort as modified', () => {
    const view = savedView();
    const search = savedViewToSearch(view);
    expect(search.view).toBe('saved:4');
    expect(search.risk_tier).toEqual(['high']);
    expect(search.sort).toBe('oldest');
    expect(activeView(search, [view])).toMatchObject({
      kind: 'saved',
      id: 4,
      label: 'High-risk CA',
      modified: false,
    });
    expect(activeView({ ...search, sort: 'queue' }, [view])).toMatchObject({ kind: 'saved', modified: true });
  });

  it('round-trips a search through a saved view', () => {
    const search = parseQueueSearch({
      view: 'x',
      risk_tier: ['high'],
      waiting: 5,
      assignee_id: [3],
      sort: 'newest',
    });
    const body = searchToSavedViewIn('Old high-risk', search, ['key', 'title']);
    expect(body).toEqual({
      name: 'Old high-risk',
      filters: { risk_tier: ['high'], waiting_more_than_days: 5, assignee_id: [3] },
      sort: 'newest',
      columns: ['key', 'title'],
    });
    const back = savedViewToSearch({ ...savedView(), ...body, id: 9 });
    expect(sameFilters(filtersOf(back), filtersOf(search))).toBe(true);
    expect(back.sort).toBe('newest');
  });

  it('ignores ItemFilter fields the queue has no control for', () => {
    const search = savedViewToSearch(
      savedView({ filters: { market: ['CA'], tag: ['q4'], status: ['approved'] }, sort: 'queue' }),
    );
    expect(search.status).toEqual(['approved']);
    expect(search).not.toHaveProperty('market');
  });
});

describe('the review screen\'s default queue order', () => {
  it('is My queue, exactly as the queue defines it', () => {
    expect(DEFAULT_TRAIL.params).toEqual(toListParams(viewSearch('mine')));
  });
});
