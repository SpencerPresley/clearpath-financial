/*
 * "Apply" on a finding (walkthrough S11): replace the finding's span in the editor with its suggested fix, when
 * the fix is literal replacement text. Suggestions come in three shapes, and only the first two are literal:
 *
 * - a whole quoted string from a code rule ('"Subject to credit approval."') or a bare figure ("9.99%–35.99%");
 * - an AI suggestion, which the prompt asks to be "replacement wording for the quoted passage when you can
 *   write one, otherwise a short concrete edit" (checks/llm/prompt.py): literal unless it reads as an
 *   instruction;
 * - an instruction ('Attach the prescreen criteria…', 'Add the APR, e.g. "12.99% APR".'), which isn't.
 *
 * Code rules also quote text meant to go *beside* the flagged span ("Show the full rate range next to this
 * lowest rate" + '"APRs from …"'). The API doesn't say which, so a quoted code suggestion only replaces a span it
 * shares a word with; additions are left for the person to place. Spans are code-point offsets (segments.ts).
 */
import type { FindingSource } from '../domain';

export interface FixableFinding {
  span: { start: number; end: number } | null;
  quote: string | null;
  suggested_fix: string | null;
  source: FindingSource;
}

const QUOTED = /^\s*["“]([^"“”]+)["”]\.?\s*$/;
const FIGURE = /^[$]?\d[\d$%.,\s–-]*%?$/;
const INSTRUCTION =
  /^(add|remove|replace|delete|drop|include|insert|say|state|use|change|show|move|disclose|clarify|mention|consider|attach|put|give|name|tell|identify|keep|rephrase|reword|avoid|label|make|specify|e\.g\.)\b/i;

/** The literal replacement text a suggestion carries, or null when it's an instruction. */
export function literalSuggestion(fix: string | null, source: FindingSource): string | null {
  const text = (fix ?? '').trim();
  if (text === '') return null;
  const quoted = QUOTED.exec(text);
  if (quoted?.[1] !== undefined) return quoted[1];
  if (FIGURE.test(text)) return text;
  if (source === 'llm' && !INSTRUCTION.test(text) && !/["“”]/.test(text)) return text;
  return null;
}

const STOP = new Set([
  'the',
  'and',
  'for',
  'you',
  'your',
  'our',
  'with',
  'are',
  'can',
  'this',
  'that',
  'from',
]);

function words(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^\p{L}\p{N}%$.]+/u)
      .map((w) => w.replace(/\.$/, ''))
      .filter((w) => w.length >= 3 && !STOP.has(w)),
  );
}

function sharesWord(a: string, b: string): boolean {
  const left = words(a);
  return [...words(b)].some((w) => left.has(w));
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

/** `text` with the finding's span replaced by its literal suggestion, or null when Apply doesn't apply. */
export function applyFix(text: string, f: FixableFinding): string | null {
  const literal = literalSuggestion(f.suggested_fix, f.source);
  if (literal === null) return null;
  const where = locate(text, f);
  if (where === null) return null;
  const current = text.slice(where.start, where.end);
  if (current === literal) return null;
  const figure = FIGURE.test(literal) && FIGURE.test(current);
  if (f.source !== 'llm' && !figure && !sharesWord(current, literal)) return null;
  return text.slice(0, where.start) + literal + text.slice(where.end);
}
