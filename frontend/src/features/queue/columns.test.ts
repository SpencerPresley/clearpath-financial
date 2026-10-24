import { describe, expect, it } from 'vitest';

import { ageTitle, formatQueueAge } from './columns';

const HOUR = 60 * 60 * 1000;
const now = new Date('2026-10-24T15:00:00Z');
const ago = (hours: number) => new Date(now.getTime() - hours * HOUR);

describe('formatQueueAge', () => {
  it('never reads "3d" for something waiting more than three days', () => {
    expect(formatQueueAge(ago(3 * 24 + 2), now)).toBe('3.1d');
    expect(formatQueueAge(ago(3 * 24 + 0.5), now)).toBe('3.1d'); // rounded up, never down to 3.0
    expect(formatQueueAge(ago(3 * 24), now)).toBe('3.0d');
    expect(formatQueueAge(ago(6 * 24 + 20), now)).toBe('6.9d');
  });

  it('keeps the compact age under a day and from a week', () => {
    expect(formatQueueAge(ago(5), now)).toBe('5h');
    expect(formatQueueAge(ago(8 * 24), now)).toBe('8d');
    expect(formatQueueAge(ago(60 * 24), now)).toBe('2mo');
  });
});

describe('ageTitle', () => {
  it('says when the item entered the queue, with the earlier submission after a reopen', () => {
    expect(
      ageTitle({ queue_entered_at: '2026-10-22T21:40:00Z', submitted_at: '2026-10-22T21:40:00Z' }),
    ).toMatch(/^In the queue since Oct 22, 2026, \d{1,2}:40 [AP]M$/);
    expect(
      ageTitle({ queue_entered_at: '2026-10-24T14:59:00Z', submitted_at: '2026-08-26T16:00:00Z' }),
    ).toMatch(/^In the queue since Oct 24, 2026, .+ · last submitted Aug 26, 2026, .+$/);
  });
});
