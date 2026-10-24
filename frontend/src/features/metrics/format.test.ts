import { describe, expect, it } from 'vitest';

import { formatHours, formatRounds, isPartial, periodFor, rangeLabel, sourceSplit } from './format';

describe('formatHours', () => {
  it.each([
    [null, '—'],
    [0, '0 h'],
    [0.4, '0.4 h'],
    [5, '5.0 h'],
    [47.9, '47.9 h'],
    [48, '2.0 d'],
    [130, '5.4 d'],
  ])('%s → %s', (hours, expected) => {
    expect(formatHours(hours)).toBe(expected);
  });
});

describe('formatRounds', () => {
  it.each([
    [null, '—'],
    [1, '1.0'],
    [1.75, '1.8'],
  ])('%s → %s', (rounds, expected) => {
    expect(formatRounds(rounds)).toBe(expected);
  });
});

describe('sourceSplit', () => {
  it('names both sources when both contribute', () => {
    expect(sourceSplit({ native_count: 30, imported_count: 12 })).toBe('30 native · 12 imported');
  });
  it('says native only when nothing was imported', () => {
    expect(sourceSplit({ native_count: 3, imported_count: 0 })).toBe('native only');
  });
  it('says imported only when nothing is native', () => {
    expect(sourceSplit({ native_count: 0, imported_count: 4 })).toBe('imported only');
  });
  it('says nothing when there is no data', () => {
    expect(sourceSplit({ native_count: 0, imported_count: 0 })).toBe('');
  });
});

describe('periodFor', () => {
  const today = new Date(2026, 9, 24); // Oct 24, 2026, local

  it('starts presets on a bucket boundary and ends today', () => {
    // Oct 24, 2026 is a Saturday; its week starts Monday Oct 19.
    expect(periodFor({ range: '4w' }, today)).toEqual({ from: '2026-09-28', to: '2026-10-24' });
    expect(periodFor({ range: '13w' }, today)).toEqual({ from: '2026-07-27', to: '2026-10-24' });
    expect(periodFor({ range: '12m' }, today)).toEqual({ from: '2025-11-01', to: '2026-10-24' });
  });

  it('uses the custom dates, falling back to the 13-week window for a missing end', () => {
    expect(periodFor({ range: 'custom', from: '2025-01-01', to: '2025-06-30' }, today)).toEqual({
      from: '2025-01-01',
      to: '2025-06-30',
    });
    expect(periodFor({ range: 'custom', from: '2025-01-01' }, today)).toEqual({
      from: '2025-01-01',
      to: '2026-10-24',
    });
  });
});

describe('rangeLabel', () => {
  const today = new Date(2026, 9, 24);

  it('leaves the year out inside the current year', () => {
    expect(rangeLabel('2026-10-19', '2026-10-24', today)).toBe('Oct 19 – Oct 24');
  });
  it('names the years when the range crosses one or is in another year', () => {
    expect(rangeLabel('2025-11-01', '2026-10-24', today)).toBe('Nov 1, 2025 – Oct 24, 2026');
    expect(rangeLabel('2025-11-01', '2025-11-30', today)).toBe('Nov 1, 2025 – Nov 30, 2025');
  });
});

describe('isPartial', () => {
  const point = (period_start: string, from_date: string, to_date: string) => ({
    period_start,
    from_date,
    to_date,
    value: null,
    native_value: null,
    imported_value: null,
    count: 0,
    native_count: 0,
    imported_count: 0,
  });

  it('is false for a whole week or month', () => {
    expect(isPartial(point('2026-10-12', '2026-10-12', '2026-10-18'), 'week')).toBe(false);
    expect(isPartial(point('2026-02-01', '2026-02-01', '2026-02-28'), 'month')).toBe(false);
  });
  it('is true for the week to date and a clipped start', () => {
    expect(isPartial(point('2026-10-19', '2026-10-19', '2026-10-24'), 'week')).toBe(true);
    expect(isPartial(point('2026-07-20', '2026-07-26', '2026-07-26'), 'week')).toBe(true);
  });
});
