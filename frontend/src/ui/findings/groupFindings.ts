import type { FindingSource, Severity } from '../domain';

export type FindingGroupId = 'blocking' | 'warning' | 'checklist';

export interface GroupableFinding {
  source: FindingSource;
  severity: Severity;
  state: 'open' | 'accepted' | 'dismissed';
  span: { start: number; end: number } | null;
}

export interface FindingGroup<T> {
  id: FindingGroupId;
  label: 'Blocking' | 'Warning' | 'Checklist';
  findings: T[];
}

const GROUPS: readonly { id: FindingGroupId; label: FindingGroup<unknown>['label'] }[] = [
  { id: 'blocking', label: 'Blocking' },
  { id: 'warning', label: 'Warning' },
  { id: 'checklist', label: 'Checklist' },
];

function groupOf(finding: GroupableFinding): FindingGroupId {
  return finding.source === 'human' ? 'checklist' : finding.severity;
}

function order(a: GroupableFinding, b: GroupableFinding): number {
  const openA = a.state === 'open' ? 0 : 1;
  const openB = b.state === 'open' ? 0 : 1;
  return openA - openB || (a.span?.start ?? Infinity) - (b.span?.start ?? Infinity);
}

/** Blocking → warning → checklist (human items, whatever their severity); open first, then by position. */
export function groupFindings<T extends GroupableFinding>(findings: readonly T[]): FindingGroup<T>[] {
  return GROUPS.map((group) => ({
    ...group,
    findings: findings.filter((finding) => groupOf(finding) === group.id).sort(order),
  })).filter((group) => group.findings.length > 0);
}

/** The groups' findings in display order: the order n/p moves through. */
export function flattenGroups<T>(groups: readonly FindingGroup<T>[]): T[] {
  return groups.flatMap((group) => group.findings);
}
