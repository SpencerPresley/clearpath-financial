import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatDayMonth, formatMonth } from './labels';

// Local times on purpose: every formatter shows the viewer's own clock, so the tests build local dates.
const AFTERNOON = new Date(2026, 9, 22, 14, 40);

describe('one date format for the whole app (walkthrough-1 nit 2)', () => {
  it('formats a date-only string as that calendar day, wherever the viewer is', () => {
    expect(formatDate('2026-07-21')).toBe('Jul 21, 2026');
  });

  it('formats a timestamp or a Date by its local day', () => {
    expect(formatDate(AFTERNOON)).toBe('Oct 22, 2026');
    expect(formatDate(AFTERNOON.toISOString())).toBe('Oct 22, 2026');
  });

  it('adds the time when it matters, in the same shape (not 10/22/2026, 2:40:00 PM)', () => {
    expect(formatDateTime(AFTERNOON)).toBe('Oct 22, 2026, 2:40 PM');
    expect(formatDateTime(AFTERNOON.toISOString())).toBe('Oct 22, 2026, 2:40 PM');
  });

  it('has short forms for chart ticks and same-year mentions', () => {
    expect(formatDayMonth('2026-10-19')).toBe('Oct 19');
    expect(formatMonth('2026-10-01')).toBe('Oct 2026');
  });

  it.each([null, undefined, '', 'not a date'])('shows a dash for %j', (value) => {
    expect(formatDate(value)).toBe('—');
    expect(formatDateTime(value)).toBe('—');
  });
});
