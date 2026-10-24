import { describe, expect, it } from 'vitest';

import type { MetricPointOut } from '../../api/generated/model';
import { chartName, chartRows } from './Trend';

function point(start: string, native: number | null, imported: number | null): MetricPointOut {
  return {
    period_start: start,
    from_date: start,
    to_date: start,
    value: null,
    native_value: native,
    imported_value: imported,
    count: (native === null ? 0 : 1) + (imported === null ? 0 : 1),
    native_count: native === null ? 0 : 1,
    imported_count: imported === null ? 0 : 1,
  };
}

describe('chartRows', () => {
  it('groups a duration by source and charts it in days once any bar passes two days', () => {
    const rows = chartRows(
      'time_to_first_review',
      [point('2026-10-01', 5, 240), point('2026-11-01', 6, null)],
      'month',
    );

    expect(rows.unit).toBe('d');
    expect(rows.sources).toEqual(['Native', 'Imported']);
    expect(rows.bars.map((b) => [b.label, b.source, b.value])).toEqual([
      ['Oct 2026', 'Native', 5 / 24],
      ['Oct 2026', 'Imported', 10],
      ['Nov 2026', 'Native', 0.25],
    ]);
  });

  it('keeps hours when every bar is under two days, and leaves gaps for empty buckets', () => {
    const rows = chartRows(
      'time_per_round',
      [point('2026-10-05', 6, null), point('2026-10-12', null, null)],
      'week',
    );

    expect(rows.unit).toBe('h');
    expect(rows.sources).toEqual(['Native']);
    expect(rows.bars).toHaveLength(1);
  });

  it('stacks throughput counts and lists only sources that contributed', () => {
    const p = { ...point('2026-10-05', null, null), native_count: 3, imported_count: 0 };
    const rows = chartRows('throughput', [p], 'week');

    expect(rows.bars.map((b) => [b.source, b.value])).toEqual([
      ['Native', 3],
      ['Imported', 0],
    ]);
    expect(rows.sources).toEqual(['Native']);
    expect(chartName('throughput', 'week', rows.sources)).toBe('Throughput by week, native only');
  });
});
