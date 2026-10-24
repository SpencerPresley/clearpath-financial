import { describe, expect, it } from 'vitest';

import { DEFAULT_COLUMN_VISIBILITY, TITLE_MIN_WIDTH } from './columns';
import type { ColumnVisibility } from './columns';
import { fitColumns, fixedWidth } from './fit';

const shown = (visibility: ColumnVisibility) =>
  ['partner', 'round', 'open_findings', 'age', 'risk_tier', 'assignee'].filter(
    (id) => visibility[id] !== false,
  );

// Region widths measured on the seeded demo (the table's scroll container, borders excluded).
const AT_1440 = 1174;
const AT_1440_ASSISTANT = 938;
const AT_1440_DRAWER = 762;
const AT_1280 = 1014;
const AT_1280_ASSISTANT = 778;
const AT_1280_DRAWER = 634;

describe('fitColumns (walkthrough-1 nit 3)', () => {
  it('keeps the designed widths when the title has room (1440, nothing open)', () => {
    const fit = fitColumns(AT_1440, DEFAULT_COLUMN_VISIBILITY, {});
    // Only the select cell widens, to the row checkbox's 40px hit area.
    expect(fit.sizing).toEqual({ select: 40 });
    expect(fit.visibility).toEqual(DEFAULT_COLUMN_VISIBILITY);
  });

  it.each([
    ['1280', AT_1280],
    ['1440 + assistant', AT_1440_ASSISTANT],
    ['1440 + drawer', AT_1440_DRAWER],
    ['1280 + assistant', AT_1280_ASSISTANT],
    ['1280 + drawer', AT_1280_DRAWER],
  ])('keeps Risk and Assignee at %s, and the title at least its minimum', (_, width) => {
    const fit = fitColumns(width, DEFAULT_COLUMN_VISIBILITY, {});
    expect(shown(fit.visibility)).toEqual(expect.arrayContaining(['risk_tier', 'assignee']));
    expect(width - fixedWidth(fit.visibility, fit.sizing)).toBeGreaterThanOrEqual(TITLE_MIN_WIDTH);
  });

  it('tightens before it hides: at 1280 every default column stays, with a wider title than before', () => {
    const fit = fitColumns(AT_1280, DEFAULT_COLUMN_VISIBILITY, {});
    expect(shown(fit.visibility)).toEqual([
      'partner',
      'round',
      'open_findings',
      'age',
      'risk_tier',
      'assignee',
    ]);
    expect(AT_1280 - fixedWidth(fit.visibility, fit.sizing)).toBeGreaterThanOrEqual(240);
  });

  it('steps columns aside lowest-priority first: round, then partner, then findings, then age', () => {
    expect(shown(fitColumns(AT_1440_ASSISTANT, DEFAULT_COLUMN_VISIBILITY, {}).visibility)).toEqual([
      'partner',
      'open_findings',
      'age',
      'risk_tier',
      'assignee',
    ]);
    expect(shown(fitColumns(AT_1280_DRAWER, DEFAULT_COLUMN_VISIBILITY, {}).visibility)).toEqual([
      'risk_tier',
      'assignee',
    ]);
  });

  it('hides extra columns someone chose before the defaults', () => {
    const chosen = { ...DEFAULT_COLUMN_VISIBILITY, tags: true, notes: true };
    const fit = fitColumns(AT_1280, chosen, {});
    expect(fit.visibility.notes).toBe(false);
    expect(fit.visibility.partner).not.toBe(false);
  });

  it('never overrides a width someone dragged, and counts it when fitting', () => {
    const fit = fitColumns(AT_1280, DEFAULT_COLUMN_VISIBILITY, { assignee: 220 });
    expect(fit.sizing.assignee).toBe(220);
    expect(AT_1280 - fixedWidth(fit.visibility, fit.sizing)).toBeGreaterThanOrEqual(TITLE_MIN_WIDTH);
  });

  it('uses the designed widths until the region has been measured', () => {
    expect(fitColumns(null, DEFAULT_COLUMN_VISIBILITY, {})).toEqual({
      visibility: DEFAULT_COLUMN_VISIBILITY,
      sizing: { select: 40 },
    });
  });
});
