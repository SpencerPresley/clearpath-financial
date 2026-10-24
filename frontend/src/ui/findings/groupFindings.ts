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

// Stable: by position in the copy, never by triage state, so cards don't move under the reviewer while
// they triage (open/resolved is shown on the card, and n/p skip nothing).
function order(a: GroupableFinding, b: GroupableFinding): number {
  const start = (f: GroupableFinding) => f.span?.start ?? Number.MAX_SAFE_INTEGER;
  return start(a) - start(b);
}

/** Blocking → warning → checklist (human items, whatever their severity); then by position in the copy. */
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
