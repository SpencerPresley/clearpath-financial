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

function markAttrs(mark: SpanMark) {
  return {
    'data-severity': mark.severity,
    'data-source': mark.source,
    'data-resolved': mark.resolved === true ? 'true' : undefined,
    'data-accepted': mark.accepted === true ? 'true' : undefined,
  };
}

/**
 * Read-only copy with flagged spans. Severity sets the fill, source sets the underline style. Where two
 * findings cover the same text, the second draws its own line under the first, so a dashed AI line on
 * a blocking code span isn't hidden.
 */
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
        const under = segment.marks[1];
        const resolved = segment.marks.every((m) => m.resolved === true);
        return (
          <mark
            key={segment.start}
            className="app-mark"
            {...markAttrs(top)}
            data-resolved={resolved ? 'true' : undefined}
            data-active={active ? 'true' : undefined}
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
            {under === undefined ? (
              segment.text
            ) : (
              <span className="app-mark-under" {...markAttrs(under)}>
                {segment.text}
              </span>
            )}
          </mark>
        );
      })}
    </div>
  );
}
