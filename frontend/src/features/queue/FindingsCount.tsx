import { Icon } from '../../ui/Icon';

export function findingsLabel(count: number): string {
  return count === 1 ? '1 open finding' : `${String(count)} open findings`;
}

/** Open-finding count for a row. Zero is muted so the eye lands on items that still need triage. */
export function FindingsCount({ count }: { count: number }) {
  return (
    <span className="app-findings-count" data-zero={count === 0 ? 'true' : undefined}>
      <Icon name="entity.finding" size={14} />
      <span className="app-figure" aria-hidden="true">
        {count}
      </span>
      <span className="sr-only">{findingsLabel(count)}</span>
    </span>
  );
}
