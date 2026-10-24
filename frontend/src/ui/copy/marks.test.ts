import { describe, expect, it } from 'vitest';

import { marksFromFindings } from './marks';

describe('marksFromFindings', () => {
  it('converts code-point spans and skips findings without a span', () => {
    const text = '💸 Rates as low as 5.99%';
    const marks = marksFromFindings(text, [
      {
        id: 7,
        span: { start: 8, end: 17 },
        quote: 'as low as',
        severity: 'blocking',
        source: 'code',
        message: 'Rate claim needs the full APR range',
      },
      {
        id: 8,
        span: null,
        quote: null,
        severity: 'warning',
        source: 'human',
        message: 'Check imagery',
      },
    ]);
    expect(marks).toHaveLength(1);
    const [mark] = marks;
    expect(mark?.id).toBe('7');
    expect(text.slice(mark?.start, mark?.end)).toBe('as low as');
    expect(mark?.label).toBe('Blocking · Code check: Rate claim needs the full APR range');
  });

  it('uses the index when findings carry no id (previews)', () => {
    const marks = marksFromFindings('as low as', [
      { span: { start: 0, end: 9 }, quote: 'as low as', severity: 'warning', source: 'code', message: 'm' },
    ]);
    expect(marks[0]?.id).toBe('preview-0');
  });
});
