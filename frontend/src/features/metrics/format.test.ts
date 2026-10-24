import { describe, expect, it } from 'vitest';

import { formatHours, formatRounds, periodFor, sourceSplit } from './format';

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

  it('ends today and counts today in the range', () => {
    expect(periodFor({ range: '4w' }, today)).toEqual({ from: '2026-09-27', to: '2026-10-24' });
    expect(periodFor({ range: '13w' }, today)).toEqual({ from: '2026-07-26', to: '2026-10-24' });
    expect(periodFor({ range: '12m' }, today)).toEqual({ from: '2025-10-25', to: '2026-10-24' });
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
