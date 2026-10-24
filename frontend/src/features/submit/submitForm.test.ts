import { describe, expect, it } from 'vitest';

import { EMPTY_SUBMIT_FORM, previewInput, submitFormSchema, toSubmitIn } from './submitForm';
import type { SubmitFormValues } from './submitForm';

const VALID: SubmitFormValues = {
  ...EMPTY_SUBMIT_FORM,
  title: 'Fall personal loan promo',
  product: 'personal_loan',
  channel: 'paid_social',
  markets: ['national'],
  planned_first_run: '2026-11-01',
  content_text: 'Personal loans as low as 5.99% APR.',
};

/** Field path -> first message, the way the form shows them. */
function errors(values: SubmitFormValues): Record<string, string> {
  const result = submitFormSchema.safeParse(values);
  if (result.success) return {};
  const out: Record<string, string> = {};
  for (const issue of result.error.issues) {
    const key = issue.path.join('.');
    out[key] ??= issue.message;
  }
  return out;
}

describe('submitFormSchema', () => {
  it('accepts a complete submission', () => {
    expect(errors(VALID)).toEqual({});
  });

  it('names every missing required field in plain words', () => {
    expect(errors(EMPTY_SUBMIT_FORM)).toEqual({
      title: 'Enter a title.',
      product: 'Choose a product.',
      channel: 'Choose a channel.',
      planned_first_run: 'Enter the first run date.',
      content_text: 'Paste or type the copy.',
    });
  });

  it('requires at least one market', () => {
    expect(errors({ ...VALID, markets: [] })).toEqual({ markets: 'Choose at least one market.' });
  });

  it('requires a partner on partner channels, on the partner field', () => {
    expect(errors({ ...VALID, channel: 'affiliate_page' })).toEqual({
      partner_id: 'Choose the partner that runs this page.',
    });
    expect(errors({ ...VALID, channel: 'affiliate_page', partner_id: 7 })).toEqual({});
  });

  it('rejects a last run before the first run, on the last-run field', () => {
    expect(errors({ ...VALID, planned_last_run: '2026-10-31' })).toEqual({
      planned_last_run: 'Last run must be on or after the first run.',
    });
    expect(errors({ ...VALID, planned_last_run: '2026-11-01' })).toEqual({});
  });

  it('requires a kind for each evidence file', () => {
    const file = new File(['x'], 'rate-sheet.pdf', { type: 'application/pdf' });
    expect(errors({ ...VALID, evidence: [{ file, kind: null }] })).toEqual({
      'evidence.0.kind': 'Choose what this file is.',
    });
  });
});

describe('toSubmitIn', () => {
  it('maps empty optional fields to null and drops a partner off partner channels', () => {
    expect(toSubmitIn({ ...VALID, partner_id: 7, planned_last_run: '' })).toEqual({
      title: 'Fall personal loan promo',
      product: 'personal_loan',
      channel: 'paid_social',
      partner_id: null,
      markets: ['national'],
      planned_first_run: '2026-11-01',
      planned_last_run: null,
      is_prescreen: false,
      content_text: 'Personal loans as low as 5.99% APR.',
      source_url: null,
    });
  });

  it('keeps the partner on a partner channel', () => {
    expect(toSubmitIn({ ...VALID, channel: 'affiliate_page', partner_id: 7 }).partner_id).toBe(7);
  });
});

describe('previewInput', () => {
  it('is null until there is copy and enough context to check it', () => {
    expect(previewInput({ ...VALID, content_text: '  ' })).toBeNull();
    expect(previewInput({ ...VALID, product: null })).toBeNull();
    expect(previewInput({ ...VALID, markets: [] })).toBeNull();
  });

  it('sends the queued file kinds, the mockup as creative', () => {
    const file = new File(['x'], 'a.pdf');
    const input = previewInput({
      ...VALID,
      mockup: new File(['x'], 'mock.png', { type: 'image/png' }),
      evidence: [
        { file, kind: 'rate_sheet' },
        { file, kind: 'rate_sheet' },
        { file, kind: null },
      ],
    });
    expect(input?.attachment_kinds).toEqual(['creative', 'rate_sheet']);
  });
});
