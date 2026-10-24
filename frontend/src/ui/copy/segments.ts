/*
 * Highlighting spans in item copy.
 *
 * Offsets: the backend (Python) indexes `content_text` by Unicode code point; JavaScript strings index by
 * UTF-16 code unit. Any astral character (emoji, some symbols) before a span shifts every later offset by
 * one, so every span from the API is converted with `toUtf16Span` / `utf16Mapper` before it becomes a
 * `SpanMark`. `SpanMark.start/end` are always UTF-16.
 */
import type { FindingSource, Severity } from '../domain';

export interface SpanMark {
  /** Stable id; review uses the finding id, previews use `preview-<n>`. */
  id: string;
  /** UTF-16 offsets into the text being rendered, `[start, end)`. */
  start: number;
  end: number;
  severity: Severity;
  source: FindingSource;
  /** The exact text the check quoted; used to hide marks that no longer match edited text. */
  quote?: string | null;
  /** Accessible description, e.g. "Blocking · Code check: Rate claim needs the APR range". */
  label: string;
  /** Accepted or dismissed: drawn quieter so open findings stand out. */
  resolved?: boolean;
  /** Accepted (must change): keeps its severity color on the quieter line, unlike a dismissal. */
  accepted?: boolean;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  /** Marks covering this segment: blocking first, then by start. The first decides the style. */
  marks: SpanMark[];
}

/** Returns a function from code-point offset to UTF-16 offset for `text`, clamped to the text's end. */
export function utf16Mapper(text: string): (codePoint: number) => number {
  const offsets: number[] = [0];
  let unit = 0;
  for (const char of text) {
    unit += char.length;
    offsets.push(unit);
  }
  const last = offsets.length - 1;
  return (codePoint: number) => offsets[Math.max(0, Math.min(codePoint, last))] ?? text.length;
}

export function toUtf16Span(
  text: string,
  span: { start: number; end: number },
): { start: number; end: number } {
  const map = utf16Mapper(text);
  return { start: map(span.start), end: map(span.end) };
}

const SEVERITY_RANK: Record<Severity, number> = { blocking: 0, warning: 1 };

// Open before resolved, then blocking before warning, then by start: the first mark styles the segment.
function byPriority(a: SpanMark, b: SpanMark): number {
  return (
    Number(a.resolved === true) - Number(b.resolved === true) ||
    SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
    a.start - b.start
  );
}

/** Splits `text` at every mark boundary; each character appears in exactly one segment. */
export function segmentText(text: string, marks: readonly SpanMark[]): Segment[] {
  if (text.length === 0) {
    return [];
  }
  const clamped = marks
    .map((m) => ({ ...m, start: Math.max(0, m.start), end: Math.min(text.length, m.end) }))
    .filter((m) => m.end > m.start);

  const boundaries = new Set<number>([0, text.length]);
  for (const m of clamped) {
    boundaries.add(m.start);
    boundaries.add(m.end);
  }
  const points = [...boundaries].sort((a, b) => a - b);

  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const start = points[i] ?? 0;
    const end = points[i + 1] ?? text.length;
    const covering = clamped.filter((m) => m.start <= start && m.end >= end).sort(byPriority);
    segments.push({ start, end, text: text.slice(start, end), marks: covering });
  }
  return segments;
}

/** Keeps marks whose quote still sits at their span (or that carry no quote). */
export function visibleMarks(text: string, marks: readonly SpanMark[]): SpanMark[] {
  return marks.filter((m) => m.quote == null || text.slice(m.start, m.end) === m.quote);
}
