import { describe, expect, it } from 'vitest';

import type { FixKind } from '../../api/generated/model';
import { applyFix } from './applyFix';
import type { FixableFinding } from './applyFix';

/** Code-point span of `quote` in `text`, as the API sends it. */
function at(text: string, quote: string): { start: number; end: number } {
  const index = text.indexOf(quote);
  const start = Array.from(text.slice(0, index)).length;
  return { start, end: start + Array.from(quote).length };
}

function finding(
  text: string,
  quote: string,
  fix_kind: FixKind | null,
  replacement_text: string | null,
): FixableFinding {
  return { span: at(text, quote), quote, fix_kind, replacement_text };
}

describe('applyFix', () => {
  it('replace swaps the span for the replacement text', () => {
    const text = 'Rates from 7.49% APR.';
    expect(applyFix(text, finding(text, '7.49%', 'replace', '9.99%'))).toBe('Rates from 9.99% APR.');
  });

  it('insert adds the text right after the span', () => {
    const text = 'Pay 0% APR for 9 months.';
    expect(applyFix(text, finding(text, '0%', 'insert', ' intro'))).toBe('Pay 0% intro APR for 9 months.');
  });

  it('offers nothing for an instruction, an unknown kind, or no fix', () => {
    const text = 'Guaranteed approval for most applicants.';
    expect(applyFix(text, finding(text, 'Guaranteed', 'instruction', null))).toBeNull();
    // Findings recorded before fix kinds: no guessing from the wording of the suggestion.
    expect(applyFix(text, finding(text, 'Guaranteed', null, null))).toBeNull();
    expect(applyFix(text, finding(text, 'Guaranteed', null, 'Subject to credit approval.'))).toBeNull();
  });

  it('needs a span and replacement text', () => {
    const text = 'Personal loans.';
    expect(
      applyFix(text, { span: null, quote: null, fix_kind: 'insert', replacement_text: ' Unsubscribe' }),
    ).toBeNull();
    expect(applyFix(text, finding(text, 'loans', 'replace', ''))).toBeNull();
    expect(applyFix(text, finding(text, 'loans', 'replace', 'loans'))).toBeNull(); // nothing would change
  });

  it('counts span offsets in code points, so an emoji before the span is safe', () => {
    const text = '🔥 Talk to a counselor today';
    expect(applyFix(text, finding(text, 'counselor', 'replace', 'loan officer'))).toBe(
      '🔥 Talk to a loan officer today',
    );
  });

  it('finds the quote again when the text moved, if it occurs once', () => {
    const original = 'Talk to a counselor today';
    const edited = `New intro. ${original}`;
    expect(applyFix(edited, finding(original, 'counselor', 'replace', 'loan officer'))).toBe(
      'New intro. Talk to a loan officer today',
    );
    const twice = 'A counselor. A counselor.';
    expect(applyFix(`x ${twice}`, finding(twice, 'counselor', 'replace', 'loan officer'))).toBeNull();
  });
});
