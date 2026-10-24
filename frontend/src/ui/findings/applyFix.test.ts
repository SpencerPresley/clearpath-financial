import { describe, expect, it } from 'vitest';

import { applyFix, literalSuggestion } from './applyFix';
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
  fix: string,
  source: FixableFinding['source'] = 'code',
): FixableFinding {
  return { span: at(text, quote), quote, suggested_fix: fix, source };
}

describe('literalSuggestion', () => {
  it('reads a whole quoted suggestion as the literal text', () => {
    expect(literalSuggestion('"Subject to credit approval."', 'code')).toBe('Subject to credit approval.');
    expect(literalSuggestion('“Get prequalified”', 'code')).toBe('Get prequalified');
    expect(literalSuggestion('"loan officer".', 'code')).toBe('loan officer');
  });

  it('reads a bare figure as the literal value', () => {
    expect(literalSuggestion('9.99%–35.99%', 'code')).toBe('9.99%–35.99%');
    expect(literalSuggestion('$1,000–$40,000', 'code')).toBe('$1,000–$40,000');
  });

  it('leaves instructions alone', () => {
    expect(literalSuggestion('Attach the prescreen criteria (kind: prescreen_criteria).', 'code')).toBeNull();
    expect(literalSuggestion('e.g. "36 monthly payments of $337".', 'code')).toBeNull();
    expect(literalSuggestion('Add the APR, e.g. "12.99% APR".', 'code')).toBeNull();
    expect(
      literalSuggestion('"#ad" or "Advertiser disclosure: we receive compensation."', 'code'),
    ).toBeNull();
    expect(literalSuggestion('', 'code')).toBeNull();
  });

  it('takes an AI suggestion as replacement wording unless it is an instruction', () => {
    // The prompt asks for "replacement wording for the quoted passage when you can write one" (checks/llm/prompt.py).
    expect(literalSuggestion('Checking your rate takes two minutes.', 'llm')).toBe(
      'Checking your rate takes two minutes.',
    );
    expect(literalSuggestion('Add “for borrowers with excellent credit”', 'llm')).toBeNull();
    expect(literalSuggestion('Remove the urgency claim.', 'llm')).toBeNull();
  });
});

describe('applyFix', () => {
  it('replaces the span with the literal suggestion', () => {
    const text = 'Guaranteed approval for most applicants. Apply today.';
    expect(applyFix(text, finding(text, 'Guaranteed approval', '"Subject to credit approval."'))).toBe(
      'Subject to credit approval. for most applicants. Apply today.',
    );
  });

  it('replaces a figure with the current one', () => {
    const text = 'Rates from 5.99% APR.';
    expect(applyFix(text, finding(text, '5.99%', '9.99%–35.99%'))).toBe('Rates from 9.99%–35.99% APR.');
  });

  it('counts span offsets in code points, so an emoji before the span is safe', () => {
    const text = '🔥 Guaranteed approval today';
    expect(applyFix(text, finding(text, 'Guaranteed approval', '"Subject to credit approval"'))).toBe(
      '🔥 Subject to credit approval today',
    );
  });

  it('finds the quote again when the text moved, if it occurs once', () => {
    const original = 'Guaranteed approval today';
    const edited = `New intro. ${original}`;
    expect(applyFix(edited, finding(original, 'Guaranteed approval', '"Subject to credit approval"'))).toBe(
      'New intro. Subject to credit approval today',
    );
    const twice = 'Guaranteed approval. Guaranteed approval.';
    expect(
      applyFix(`x ${twice}`, finding(twice, 'Guaranteed approval', '"Subject to credit approval"')),
    ).toBeNull();
  });

  it('does not turn a suggested addition into a replacement', () => {
    // "Show the full rate range next to this lowest rate": the quoted range goes beside the claim, not over it.
    const text = 'Rates as low as 5.99% APR.';
    expect(applyFix(text, finding(text, 'as low as 5.99% APR', '"APRs from 9.99% to 35.99%"'))).toBeNull();
    // "Say that the lowest rates go to the most creditworthy applicants."
    expect(
      applyFix(
        text,
        finding(
          text,
          'as low as 5.99%',
          '"Your rate depends on your creditworthiness; the lowest rates are for the most qualified applicants."',
        ),
      ),
    ).toBeNull();
  });

  it('needs a span, and something to change', () => {
    const text = 'Rates from 9.99% APR.';
    expect(
      applyFix(text, { span: null, quote: null, suggested_fix: '"Unsubscribe"', source: 'code' }),
    ).toBeNull();
    expect(applyFix(text, finding(text, '9.99%', '9.99%'))).toBeNull();
  });
});
