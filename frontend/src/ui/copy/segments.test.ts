import { describe, expect, it } from 'vitest';

import { segmentText, toUtf16Span, utf16Mapper, visibleMarks } from './segments';
import type { SpanMark } from './segments';

function mark(id: string, start: number, end: number, overrides: Partial<SpanMark> = {}): SpanMark {
  return { id, start, end, severity: 'warning', source: 'code', label: id, ...overrides };
}

/** Python-style (code point) index of `quote` in `text`. */
function codePointIndex(text: string, quote: string): number {
  return Array.from(text.slice(0, text.indexOf(quote))).length;
}

describe('toUtf16Span', () => {
  it('maps code-point offsets after an emoji onto the quoted UTF-16 range', () => {
    const text = 'Get 💸 cash as low as 5.99% APR';
    const start = codePointIndex(text, 'as low as');
    const span = toUtf16Span(text, { start, end: start + 'as low as'.length });

    expect(text.slice(span.start, span.end)).toBe('as low as');
    expect(span.start).toBe(start + 1); // the emoji is two UTF-16 units, one code point
  });

  it('keeps an astral character inside a span whole', () => {
    const text = 'Fast 🚀 approval';
    const span = toUtf16Span(text, { start: 5, end: 6 });
    expect(text.slice(span.start, span.end)).toBe('🚀');
  });

  it('is the identity for BMP-only text', () => {
    expect(toUtf16Span('as low as 5.99%', { start: 3, end: 6 })).toEqual({ start: 3, end: 6 });
  });

  it('clamps offsets past the end', () => {
    const text = 'a💸b';
    expect(toUtf16Span(text, { start: 1, end: 99 })).toEqual({ start: 1, end: text.length });
  });

  it('maps many offsets with one pass', () => {
    const text = '💸💸 rate';
    const map = utf16Mapper(text);
    expect([map(0), map(1), map(2), map(3)]).toEqual([0, 2, 4, 5]);
  });
});

describe('segmentText', () => {
  it('returns one plain segment without marks', () => {
    expect(segmentText('plain copy', [])).toEqual([{ start: 0, end: 10, text: 'plain copy', marks: [] }]);
  });

  it('splits around disjoint marks', () => {
    const a = mark('a', 0, 3);
    const b = mark('b', 6, 9);
    const segments = segmentText('abc---def', [b, a]);
    expect(segments.map((s) => [s.text, s.marks.map((m) => m.id)])).toEqual([
      ['abc', ['a']],
      ['---', []],
      ['def', ['b']],
    ]);
  });

  it('handles a blocking code span nested in an AI warning span, blocking first', () => {
    const outer = mark('ai', 5, 30, { severity: 'warning', source: 'llm' });
    const inner = mark('code', 10, 20, { severity: 'blocking', source: 'code' });
    const text = 'x'.repeat(40);
    const segments = segmentText(text, [outer, inner]);

    expect(segments.map((s) => [s.start, s.end, s.marks.map((m) => m.id)])).toEqual([
      [0, 5, []],
      [5, 10, ['ai']],
      [10, 20, ['code', 'ai']],
      [20, 30, ['ai']],
      [30, 40, []],
    ]);
    // Every character renders exactly once.
    expect(segments.map((s) => s.text).join('')).toBe(text);
  });

  it('merges identical spans into one segment with both marks', () => {
    const segments = segmentText('abcdef', [mark('a', 1, 4), mark('b', 1, 4)]);
    expect(segments.map((s) => s.marks.length)).toEqual([0, 2, 0]);
  });

  it('clamps marks past the end and drops empty or inverted ones', () => {
    const segments = segmentText('abcdef', [mark('long', 4, 99), mark('empty', 2, 2), mark('bad', 5, 1)]);
    expect(segments.map((s) => [s.text, s.marks.map((m) => m.id)])).toEqual([
      ['abcd', []],
      ['ef', ['long']],
    ]);
  });

  it('returns nothing for empty text', () => {
    expect(segmentText('', [mark('a', 0, 2)])).toEqual([]);
  });
});

describe('visibleMarks', () => {
  it('drops a mark whose quote no longer sits at its span', () => {
    const text = 'Rates as low as 5.99%';
    const stale = mark('stale', 0, 5, { quote: 'as low' });
    const fresh = mark('fresh', 6, 15, { quote: 'as low as' });
    const unquoted = mark('whole', 0, 0, { quote: null });
    expect(visibleMarks(text, [stale, fresh, unquoted]).map((m) => m.id)).toEqual(['fresh', 'whole']);
  });
});
