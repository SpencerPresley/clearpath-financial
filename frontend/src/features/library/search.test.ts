import { describe, expect, it } from 'vitest';

import {
  exportBody,
  hasFilters,
  librarySearchSchema,
  toItemFilter,
  toListParams,
  toSearchParams,
} from './search';

const parse = (raw: Record<string, unknown>) => librarySearchSchema.parse(raw);

describe('library search params', () => {
  it('opens the approved view with phrase mode and legacy included', () => {
    expect(parse({})).toEqual({ tab: 'approved', mode: 'phrase', legacy: 'include' });
  });

  it('drops bad fields instead of failing the route', () => {
    const search = parse({
      tab: 'archive',
      mode: 'regex',
      product: ['credit_card', 'boats'],
      partner_id: ['x'],
      approved_from: '2026-13-45',
      run_to: 'soon',
      legacy: 'maybe',
    });
    expect(search).toEqual({ tab: 'approved', mode: 'phrase', legacy: 'include', product: ['credit_card'] });
  });

  it('maps the URL onto ItemFilter: date range as [from, day after to), legacy as is_legacy', () => {
    const search = parse({
      product: ['personal_loan'],
      channel: ['email'],
      partner_id: [12],
      approved_from: '2026-01-01',
      approved_to: '2026-03-31',
      run_from: '2026-11-01',
      run_to: '2026-12-31',
      legacy: 'exclude',
    });
    expect(toItemFilter(search)).toEqual({
      product: ['personal_loan'],
      channel: ['email'],
      partner_id: [12],
      approved_after: '2026-01-01T00:00:00Z',
      approved_before: '2026-04-01T00:00:00Z',
      run_from: '2026-11-01',
      run_to: '2026-12-31',
      is_legacy: false,
    });
    expect(toItemFilter(parse({ legacy: 'only' }))).toEqual({ is_legacy: true });
    expect(toItemFilter(parse({}))).toEqual({});
  });

  it('lists the approved-to-run scope, newest change first', () => {
    expect(toListParams(parse({ product: ['credit_card'] }), 'abc')).toEqual({
      scope: 'approved_to_run',
      sort: 'updated',
      limit: 50,
      cursor: 'abc',
      product: ['credit_card'],
    });
  });

  it('searches precedents with the query, mode, and the same filters', () => {
    expect(
      toSearchParams(parse({ tab: 'precedents', query: ' credit score ', mode: 'text', legacy: 'exclude' })),
    ).toEqual({
      query: 'credit score',
      mode: 'text',
      limit: 50,
      is_legacy: false,
    });
  });

  it('exports the approved view: its filters plus status approved, in its sort', () => {
    expect(exportBody(parse({ channel: ['sms'] }), true)).toEqual({
      filters: { channel: ['sms'], status: ['approved'] },
      sort: 'updated',
      include_evidence_packs: true,
    });
  });

  it('knows when any filter is set', () => {
    expect(hasFilters(parse({}))).toBe(false);
    expect(hasFilters(parse({ legacy: 'only' }))).toBe(true);
    expect(hasFilters(parse({ run_from: '2026-11-01' }))).toBe(true);
    expect(hasFilters(parse({ query: 'x', mode: 'text', tab: 'precedents' }))).toBe(false);
  });
});
