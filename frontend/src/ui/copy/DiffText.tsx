import type { DiffSegmentOut } from '../../api/generated/model';
import { cx } from '../cx';

/**
 * A word diff rendered inline. Insertions are underlined on a neutral tint, deletions struck through in
 * muted text: shape carries the meaning, and no status color is borrowed (spec §5.2).
 */
export function DiffText({
  segments,
  className,
}: {
  segments: readonly DiffSegmentOut[];
  className?: string;
}) {
  return (
    <div className={cx('app-copy', className)}>
      {segments.map((segment, index) => {
        const key = `${String(index)}-${segment.op}`;
        if (segment.op === 'insert') {
          return (
            <ins key={key} className="app-diff-ins">
              <span className="sr-only">added: </span>
              {segment.text}
            </ins>
          );
        }
        if (segment.op === 'delete') {
          return (
            <del key={key} className="app-diff-del">
              <span className="sr-only">removed: </span>
              {segment.text}
            </del>
          );
        }
        return <span key={key}>{segment.text}</span>;
      })}
    </div>
  );
}

/** "3 changes" for a diff summary line; counts contiguous insert/delete runs as one change. */
export function countChanges(segments: readonly DiffSegmentOut[]): number {
  let changes = 0;
  let inChange = false;
  for (const segment of segments) {
    const changed = segment.op !== 'equal';
    if (changed && !inChange) {
      changes += 1;
    }
    inChange = changed;
  }
  return changes;
}
