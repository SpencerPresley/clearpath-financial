import { describe, expect, it } from 'vitest';

import { wordDiff } from './wordDiff';

describe('wordDiff', () => {
  it('marks only the changed rate', () => {
    expect(wordDiff('as low as 5.99% APR', 'as low as 6.49% APR')).toEqual([
      { op: 'equal', text: 'as low as ' },
      { op: 'delete', text: '5.99' },
      { op: 'insert', text: '6.49' },
      { op: 'equal', text: '% APR' },
    ]);
  });

  it('folds short unchanged words between changes into one rewritten phrase', () => {
    const segments = wordDiff(
      'Check your rate in 2 minutes with no impact on your credit score.',
      'Check your rate in 2 minutes; checking your rate won’t affect your credit score.',
    );
    expect(segments).toEqual([
      { op: 'equal', text: 'Check your rate in 2 minutes' },
      { op: 'delete', text: ' with no impact on ' },
      { op: 'insert', text: '; checking your rate won’t affect ' },
      { op: 'equal', text: 'your credit score.' },
    ]);
  });

  it('returns one equal segment for identical text', () => {
    expect(wordDiff('same copy', 'same copy')).toEqual([{ op: 'equal', text: 'same copy' }]);
  });

  it('round-trips both sides', () => {
    const before = 'Check your rate.\nNo impact on your credit score.';
    const after = 'Check your rate.\nChecking your rate won’t affect your credit score.';
    const segments = wordDiff(before, after);
    const side = (skip: 'insert' | 'delete') =>
      segments
        .filter((s) => s.op !== skip)
        .map((s) => s.text)
        .join('');
    expect(side('insert')).toBe(before);
    expect(side('delete')).toBe(after);
  });
});
