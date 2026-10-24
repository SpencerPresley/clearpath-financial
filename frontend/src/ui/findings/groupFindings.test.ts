import { describe, expect, it } from 'vitest';

import { flattenGroups, groupFindings } from './groupFindings';
import type { GroupableFinding } from './groupFindings';

function f(id: number, overrides: Partial<GroupableFinding> = {}): GroupableFinding & { id: number } {
  return {
    id,
    source: 'code',
    severity: 'blocking',
    state: 'open',
    span: { start: id, end: id + 1 },
    ...overrides,
  };
}

describe('groupFindings', () => {
  it('orders blocking, warning, checklist and omits empty groups', () => {
    const groups = groupFindings([
      f(1, { severity: 'warning' }),
      f(2, { source: 'human', severity: 'warning', span: null }),
      f(3),
    ]);
    expect(groups.map((g) => [g.id, g.label, g.findings.map((x) => x.id)])).toEqual([
      ['blocking', 'Blocking', [3]],
      ['warning', 'Warning', [1]],
      ['checklist', 'Checklist', [2]],
    ]);
    expect(groupFindings([f(1)]).map((g) => g.id)).toEqual(['blocking']);
  });

  it('puts human findings in the checklist even when blocking', () => {
    expect(groupFindings([f(1, { source: 'human' })])[0]?.id).toBe('checklist');
  });

  it('lists open before resolved, then by position', () => {
    const groups = groupFindings([
      f(5, { state: 'accepted', span: { start: 0, end: 2 } }),
      f(6, { span: { start: 40, end: 42 } }),
      f(7, { span: { start: 10, end: 12 } }),
      f(8, { span: null }),
    ]);
    expect(flattenGroups(groups).map((x) => x.id)).toEqual([7, 6, 8, 5]);
  });
});
