import { afterEach, describe, expect, it } from 'vitest';

import { DEFAULT_TRAIL, nextInQueue, readQueueTrail, rememberQueueTrail } from './queueTrail';

describe('nextInQueue', () => {
  it('takes the next row while the item is still in the view', () => {
    expect(nextInQueue(2, [1, 2, 3], [1, 2, 3])).toBe(3);
  });

  it('after a decision took the item out of the view, continues from where it was', () => {
    // CP-2 was third; decided, it left. The reviewer skipped 1 and 5, so 3 comes next, not 1.
    expect(nextInQueue(2, [1, 5, 3, 4], [1, 5, 2, 3, 4])).toBe(3);
  });

  it('wraps to rows skipped earlier once the end of the view is reached', () => {
    expect(nextInQueue(4, [1, 3, 4], [1, 3, 4])).toBe(1);
    expect(nextInQueue(4, [1, 3], [1, 3, 4])).toBe(1);
  });

  it('starts at the top when the item was never in the view', () => {
    expect(nextInQueue(9, [1, 3], [])).toBe(1);
  });

  it('is null when nothing else is left', () => {
    expect(nextInQueue(2, [2], [2])).toBeNull();
    expect(nextInQueue(2, [], [1, 2])).toBeNull();
  });
});

describe('queue trail storage', () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it('round-trips the view the queue showed', () => {
    const trail = { params: { mine: true, sort: 'oldest' as const }, ids: [4, 2], href: '/queue?view=mine' };
    rememberQueueTrail(trail);
    expect(readQueueTrail()).toEqual(trail);
  });

  it('falls back to My queue when nothing (or junk) is stored', () => {
    expect(readQueueTrail()).toEqual(DEFAULT_TRAIL);
    sessionStorage.setItem('clearpath.queueTrail', '{"ids":"nope"}');
    expect(readQueueTrail()).toEqual(DEFAULT_TRAIL);
    sessionStorage.setItem('clearpath.queueTrail', JSON.stringify({ params: {}, ids: [], href: 'https://evil' }));
    expect(readQueueTrail()).toEqual(DEFAULT_TRAIL);
  });
});
