import { cx } from '../cx';
import { segmentText } from './segments';
import type { Segment, SpanMark } from './segments';

export interface HighlightedTextProps {
  text: string;
  marks: readonly SpanMark[];
  /** The focused finding; its mark gets data-active and an outline. */
  activeId?: string | null;
  /** Called with the mark to focus. On overlapping marks, repeated clicks cycle through them. */
  onMarkPress?: (id: string) => void;
  /** Prefix for aria-describedby targets (`${describedByPrefix}${id}`), e.g. the finding cards. */
  describedByPrefix?: string;
  className?: string;
}

function nextMark(segment: Segment, activeId: string | null | undefined): SpanMark | undefined {
  const index = segment.marks.findIndex((m) => m.id === activeId);
  return segment.marks[index === -1 ? 0 : (index + 1) % segment.marks.length];
}

/** Read-only copy with flagged spans. Severity sets the fill, source sets the underline style. */
export function HighlightedText({
  text,
  marks,
  activeId,
  onMarkPress,
  describedByPrefix,
  className,
}: HighlightedTextProps) {
  return (
    <div className={cx('app-copy', className)}>
      {segmentText(text, marks).map((segment) => {
        const top = segment.marks[0];
        if (top === undefined) {
          return <span key={segment.start}>{segment.text}</span>;
        }
        const active = segment.marks.some((m) => m.id === activeId);
        return (
          <mark
            key={segment.start}
            className="app-mark"
            data-severity={top.severity}
            data-source={top.source}
            data-active={active ? 'true' : undefined}
            data-resolved={segment.marks.every((m) => m.resolved === true) ? 'true' : undefined}
            data-clickable={onMarkPress === undefined ? undefined : 'true'}
            data-mark-ids={segment.marks.map((m) => m.id).join(' ')}
            title={segment.marks.map((m) => m.label).join('\n')}
            aria-describedby={
              describedByPrefix === undefined
                ? undefined
                : segment.marks.map((m) => `${describedByPrefix}${m.id}`).join(' ')
            }
            onClick={
              onMarkPress === undefined
                ? undefined
                : () => {
                    const target = nextMark(segment, activeId);
                    if (target !== undefined) {
                      onMarkPress(target.id);
                    }
                  }
            }
          >
            {segment.text}
          </mark>
        );
      })}
    </div>
  );
}
