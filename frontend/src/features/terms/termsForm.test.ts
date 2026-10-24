import { describe, expect, it } from 'vitest';

import type { CreditCardTerms, PersonalLoanTerms } from '../../api/generated/model';
import {
  ccFormFrom,
  ccFormSchema,
  ccValuesFrom,
  normalizeDecimal,
  plFormFrom,
  plFormSchema,
  plValuesFrom,
  sameTerms,
  termsChanges,
  termsKey,
} from './termsForm';

const PL: PersonalLoanTerms = {
  product: 'personal_loan',
  apr_min: '7.49',
  apr_max: '35.99',
  amount_min: '1000',
  amount_max: '50000',
  term_months: [24, 36, 60],
  origination_fee_min_pct: '0',
  origination_fee_max_pct: '8',
};

const CC: CreditCardTerms = {
  product: 'credit_card',
  purchase_apr_min: '19.24',
  purchase_apr_max: '29.24',
  purchase_apr_variable: true,
  intro_apr: '0',
  intro_months: 15,
  balance_transfer_fee_pct: '3',
  annual_fee: '0',
  issuing_bank: 'Coastal Community Bank',
};

function issues(result: {
  success: boolean;
  error?: { issues: { path: PropertyKey[]; message: string }[] };
}) {
  return Object.fromEntries((result.error?.issues ?? []).map((i) => [String(i.path[0]), i.message]));
}

describe('personal loan form', () => {
  it('round-trips the current values', () => {
    expect(plValuesFrom(plFormFrom(PL))).toEqual(PL);
  });

  it('reads term months as a list, sorted and de-duplicated', () => {
    const form = { ...plFormFrom(PL), term_months: '60, 36 36,24' };
    expect(plValuesFrom(form)?.term_months).toEqual([24, 36, 60]);
  });

  it('refuses an APR outside (0, 100) and a fee at or above 100%', () => {
    const form = { ...plFormFrom(PL), apr_min: '0', apr_max: '100', origination_fee_max_pct: '100' };
    const errors = issues(plFormSchema.safeParse(form));
    expect(errors.apr_min).toBe('Enter an APR above 0% and below 100%.');
    expect(errors.apr_max).toBe('Enter an APR above 0% and below 100%.');
    expect(errors.origination_fee_max_pct).toBe('Enter a percentage from 0% up to 100%.');
  });

  it('puts min > max on the max field, for every range', () => {
    const form = {
      ...plFormFrom(PL),
      apr_min: '12',
      apr_max: '9.99',
      amount_min: '5000',
      amount_max: '1000',
      origination_fee_min_pct: '5',
      origination_fee_max_pct: '1',
    };
    const errors = issues(plFormSchema.safeParse(form));
    expect(errors.apr_max).toBe('APR max must be at least APR min.');
    expect(errors.amount_max).toBe('Amount max must be at least amount min.');
    expect(errors.origination_fee_max_pct).toBe('Origination fee max must be at least the min.');
  });

  it('needs at least one whole number of months and a positive amount', () => {
    const form = { ...plFormFrom(PL), term_months: '36, 4.5', amount_min: '0' };
    const errors = issues(plFormSchema.safeParse(form));
    expect(errors.term_months).toBe('List loan terms in whole months, e.g. 24, 36, 60.');
    expect(errors.amount_min).toBe('Enter an amount above $0.');
    expect(issues(plFormSchema.safeParse({ ...plFormFrom(PL), term_months: ' ' })).term_months).toBe(
      'List loan terms in whole months, e.g. 24, 36, 60.',
    );
  });

  it('refuses text where a number goes', () => {
    expect(issues(plFormSchema.safeParse({ ...plFormFrom(PL), apr_min: '7,49%' })).apr_min).toBe(
      'Enter a number, e.g. 7.49.',
    );
  });
});

describe('credit card form', () => {
  it('round-trips, with no intro offer as empty fields', () => {
    expect(ccValuesFrom(ccFormFrom(CC))).toEqual(CC);
    const none = { ...CC, intro_apr: null, intro_months: null };
    expect(ccFormFrom(none).intro_apr).toBe('');
    expect(ccValuesFrom(ccFormFrom(none))).toEqual(none);
  });

  it('needs intro APR and intro months together', () => {
    const errors = issues(ccFormSchema.safeParse({ ...ccFormFrom(CC), intro_months: '' }));
    expect(errors.intro_months).toBe('Set the intro period with the intro APR, or clear both.');
    const other = issues(ccFormSchema.safeParse({ ...ccFormFrom(CC), intro_apr: '' }));
    expect(other.intro_apr).toBe('Set the intro APR with the intro period, or clear both.');
  });

  it('puts purchase APR min > max on the max field and needs an issuing bank', () => {
    const errors = issues(
      ccFormSchema.safeParse({ ...ccFormFrom(CC), purchase_apr_min: '30', issuing_bank: '  ' }),
    );
    expect(errors.purchase_apr_max).toBe('Purchase APR max must be at least the min.');
    expect(errors.issuing_bank).toBe('Name the issuing bank.');
  });
});

describe('comparing terms', () => {
  it('normalizes decimals the way the backend compares them', () => {
    expect(normalizeDecimal('7.490')).toBe('7.49');
    expect(normalizeDecimal('08.0')).toBe('8');
    expect(normalizeDecimal('0.00')).toBe('0');
    expect(sameTerms(PL, { ...PL, apr_min: '7.490', amount_min: '1000.00' })).toBe(true);
    expect(termsKey(PL)).toBe(termsKey({ ...PL, apr_min: '7.490' }));
  });

  it('sees fields that impact preview does not list, like the issuing bank', () => {
    expect(sameTerms(CC, { ...CC, issuing_bank: 'Other Bank' })).toBe(false);
    expect(sameTerms(CC, { ...CC, purchase_apr_variable: false })).toBe(false);
  });

  it('lists what changed, with display values', () => {
    expect(termsChanges(PL, { ...PL, apr_min: '12.99', term_months: [36, 60] })).toEqual([
      { field: 'apr_min', label: 'APR min', from: '7.49%', to: '12.99%' },
      { field: 'term_months', label: 'Terms', from: '24, 36, 60 months', to: '36, 60 months' },
    ]);
    expect(termsChanges(CC, { ...CC, intro_apr: null, intro_months: null, annual_fee: '95' })).toEqual([
      { field: 'intro_apr', label: 'Intro APR', from: '0%', to: 'None' },
      { field: 'intro_months', label: 'Intro period', from: '15 months', to: 'None' },
      { field: 'annual_fee', label: 'Annual fee', from: '$0', to: '$95' },
    ]);
  });
});
