/*
 * "Apply" on a finding (walkthrough S11): the API says what the fix does (`fix_kind`), so nothing here guesses
 * from the suggestion's wording.
 *
 * - replace: `replacement_text` goes in place of the finding's span;
 * - insert: `replacement_text` goes right after the span (it carries its own leading space or punctuation);
 * - instruction, or null (a finding recorded before fix kinds): advice for the person, no Apply.
 *
 * Spans are code-point offsets (segments.ts).
 */
import type { FixKind } from '../../api/generated/model';

export interface FixableFinding {
  span: { start: number; end: number } | null;
  quote: string | null;
  fix_kind: FixKind | null;
  replacement_text: string | null;
}

/** UTF-16 [start, end) of the finding's text in `text`: its span if the quote is still there, else its only copy. */
function locate(text: string, f: FixableFinding): { start: number; end: number } | null {
  if (f.span === null) return null;
  const points = Array.from(text);
  const start = points.slice(0, f.span.start).join('').length;
  const end = start + points.slice(f.span.start, f.span.end).join('').length;
  const atSpan = text.slice(start, end);
  if (f.quote === null || f.quote === '') return f.span.end > f.span.start ? { start, end } : null;
  if (atSpan === f.quote) return { start, end };
  const first = text.indexOf(f.quote);
  if (first === -1 || text.includes(f.quote, first + 1)) return null;
  return { start: first, end: first + f.quote.length };
}

/** `text` with the finding's fix applied, or null when the finding has no literal fix (no Apply). */
export function applyFix(text: string, f: FixableFinding): string | null {
  const literal = f.replacement_text ?? '';
  if ((f.fix_kind !== 'replace' && f.fix_kind !== 'insert') || literal === '') return null;
  const where = locate(text, f);
  if (where === null) return null;
  const next =
    f.fix_kind === 'replace'
      ? text.slice(0, where.start) + literal + text.slice(where.end)
      : text.slice(0, where.end) + literal + text.slice(where.end);
  return next === text ? null : next;
}
