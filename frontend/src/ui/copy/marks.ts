import { SEVERITY_META, SOURCE_META } from '../badges';
import type { FindingSource, Severity } from '../domain';
import { utf16Mapper } from './segments';
import type { SpanMark } from './segments';

/** The fields of a stored finding (`FindingOut`) or a preview (`FindingDraftOut`) that a mark needs. */
export interface MarkableFinding {
  id?: number;
  span: { start: number; end: number } | null;
  quote: string | null;
  severity: Severity;
  source: FindingSource;
  message: string;
}

/** Spans arrive as code-point offsets (Python); marks are UTF-16 (see segments.ts). */
export function marksFromFindings(text: string, findings: readonly MarkableFinding[]): SpanMark[] {
  const map = utf16Mapper(text);
  const marks: SpanMark[] = [];
  findings.forEach((finding, index) => {
    if (finding.span === null) {
      return;
    }
    marks.push({
      id: finding.id === undefined ? `preview-${String(index)}` : String(finding.id),
      start: map(finding.span.start),
      end: map(finding.span.end),
      severity: finding.severity,
      source: finding.source,
      quote: finding.quote,
      label: `${SEVERITY_META[finding.severity].label} · ${SOURCE_META[finding.source].label}: ${finding.message}`,
    });
  });
  return marks;
}
