/*
 * Loading placeholders that match final layouts (spec §5.3: no content jumping). Rows use the same
 * --spacing-row height as table rows; pass the table's real column widths so nothing shifts on load.
 */

export function SkeletonText({ width = '8rem' }: { width?: string }) {
  return <span className="app-skeleton" style={{ width }} aria-hidden="true" />;
}

export function SkeletonBadge() {
  return <span className="app-skeleton-badge" aria-hidden="true" />;
}

export interface SkeletonTableProps {
  rows: number;
  /** One CSS width per column (e.g. '6rem', '1fr'); use the real table's widths. */
  columns: readonly string[];
  /** Spoken once for the whole block. */
  label?: string;
}

export function SkeletonTable({ rows, columns, label = 'Loading' }: SkeletonTableProps) {
  const template = columns.join(' ');
  return (
    <div role="status" aria-label={label} aria-busy="true" className="app-skeleton-table">
      {Array.from({ length: rows }, (_, row) => (
        <div
          key={row}
          className="app-skeleton-row"
          aria-hidden="true"
          style={{ display: 'grid', gridTemplateColumns: template }}
        >
          {columns.map((_, column) => (
            // Vary widths per row so the placeholder reads as text, not a grid of bars.
            <span
              key={column}
              className="app-skeleton"
              style={{ width: `${String(55 + ((row * 17 + column * 29) % 40))}%` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
