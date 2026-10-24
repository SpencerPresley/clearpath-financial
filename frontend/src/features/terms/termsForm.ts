/*
 * Offer terms values per product (spec §4.2 ruling 1; backend core.domain PersonalLoanTerms / CreditCardTerms):
 * the edit forms' values, the zod schemas that mirror the backend validators, the mapping to the API body, and
 * how two versions compare.
 *
 * Decimals travel as strings ("7.49"), as the API sends them. The backend refuses values identical to the
 * version in effect by comparing Decimals ("7.49" == "7.490"), across every field, including the two that
 * impact preview's `changed_fields` leaves out (issuing bank, variable APR). `sameTerms` does the same, so the
 * form can tell "nothing changed" without a round trip.
 */
import { z } from 'zod';

import type { CreditCardTerms, PersonalLoanTerms, TermsField } from '../../api/generated/model';

export type TermsValues = PersonalLoanTerms | CreditCardTerms;
export type TermsProduct = 'personal_loan' | 'credit_card';

// ---- Field metadata ----------------------------------------------------------------------------------

export type FieldKind = 'apr' | 'percent' | 'money' | 'months_list' | 'months' | 'variable' | 'text';

export interface TermsFieldDef<K extends string> {
  key: K;
  label: string;
  kind: FieldKind;
  /** Shown under the input. */
  hint?: string;
}

type PlKey = Exclude<keyof PersonalLoanTerms, 'product'>;
type CcKey = Exclude<keyof CreditCardTerms, 'product'>;

export const PL_FIELDS: readonly TermsFieldDef<PlKey>[] = [
  { key: 'apr_min', label: 'APR min', kind: 'apr' },
  { key: 'apr_max', label: 'APR max', kind: 'apr' },
  { key: 'amount_min', label: 'Amount min', kind: 'money' },
  { key: 'amount_max', label: 'Amount max', kind: 'money' },
  { key: 'term_months', label: 'Loan terms (months)', kind: 'months_list', hint: 'Separated by commas.' },
  { key: 'origination_fee_min_pct', label: 'Origination fee min', kind: 'percent' },
  { key: 'origination_fee_max_pct', label: 'Origination fee max', kind: 'percent' },
];

export const CC_FIELDS: readonly TermsFieldDef<CcKey>[] = [
  { key: 'purchase_apr_min', label: 'Purchase APR min', kind: 'apr' },
  { key: 'purchase_apr_max', label: 'Purchase APR max', kind: 'apr' },
  { key: 'purchase_apr_variable', label: 'Purchase APR type', kind: 'variable' },
  { key: 'intro_apr', label: 'Intro APR', kind: 'percent', hint: 'Leave empty for no intro offer.' },
  { key: 'intro_months', label: 'Intro period', kind: 'months' },
  { key: 'balance_transfer_fee_pct', label: 'Balance transfer fee', kind: 'percent' },
  { key: 'annual_fee', label: 'Annual fee', kind: 'money' },
  { key: 'issuing_bank', label: 'Issuing bank', kind: 'text' },
];

export function fieldsFor(product: TermsProduct): readonly TermsFieldDef<string>[] {
  return product === 'personal_loan' ? PL_FIELDS : CC_FIELDS;
}

/** What a claim in copy quotes (impact preview's `quoted_fields`, `changed_fields`). */
export const TERMS_FIELD_LABELS: Record<TermsField, string> = {
  apr_min: 'APR min',
  apr_max: 'APR max',
  amount_min: 'Amount min',
  amount_max: 'Amount max',
  term_months: 'Loan terms (months)',
  origination_fee_min_pct: 'Origination fee min',
  origination_fee_max_pct: 'Origination fee max',
  purchase_apr_min: 'Purchase APR min',
  purchase_apr_max: 'Purchase APR max',
  intro_apr: 'Intro APR',
  intro_months: 'Intro period',
  balance_transfer_fee_pct: 'Balance transfer fee',
  annual_fee: 'Annual fee',
  example_amount: 'Example amount',
  example_term_months: 'Example term',
  example_apr: 'Example APR',
  example_payment: 'Example payment',
};

// ---- Display -----------------------------------------------------------------------------------------

/** "7.490" → "7.49", "08.0" → "8": the canonical form of a decimal string (equal Decimals, equal strings). */
export function normalizeDecimal(value: string): string {
  const trimmed = value.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return trimmed;
  const [whole = '0', fraction = ''] = trimmed.split('.');
  const int = whole.replace(/^0+(?=\d)/, '');
  const frac = fraction.replace(/0+$/, '');
  return frac === '' ? int : `${int}.${frac}`;
}

const MONEY = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

function months(n: number): string {
  return `${String(n)} ${n === 1 ? 'month' : 'months'}`;
}

function asText(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : JSON.stringify(value);
}

/** One field's value as the UI shows it: "7.49%", "$50,000", "24, 36, 60 months", "None". */
export function formatTermsValue(kind: FieldKind, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'None';
  switch (kind) {
    case 'apr':
    case 'percent':
      return `${normalizeDecimal(asText(value))}%`;
    case 'money': {
      const n = Number(value);
      const fixed = Number.isInteger(n)
        ? MONEY.format(n)
        : n.toLocaleString('en-US', { minimumFractionDigits: 2 });
      return `$${fixed}`;
    }
    case 'months_list':
      return Array.isArray(value) ? `${value.join(', ')} months` : asText(value);
    case 'months':
      return months(Number(value));
    case 'variable':
      return value === true ? 'Variable' : 'Fixed';
    case 'text':
      return asText(value);
  }
}

/** The terms as the read-only view lists them; a credit card's intro offer reads as one line. */
export function displayRows(values: TermsValues): { label: string; value: string }[] {
  const record = values as unknown as Record<string, unknown>;
  const rows = fieldsFor(values.product ?? 'personal_loan')
    .filter((def) => def.key !== 'intro_months')
    .map((def) => ({ label: def.label, value: formatTermsValue(def.kind, record[def.key]) }));
  if (values.product === 'credit_card') {
    const intro = rows.find((row) => row.label === 'Intro APR');
    if (intro !== undefined) {
      intro.label = 'Intro offer';
      intro.value =
        values.intro_apr === null || values.intro_apr === undefined || values.intro_months == null
          ? 'None'
          : `${normalizeDecimal(values.intro_apr)}% for ${months(values.intro_months)}`;
    }
  }
  return rows;
}

// ---- Forms -------------------------------------------------------------------------------------------

export interface PlFormValues {
  apr_min: string;
  apr_max: string;
  amount_min: string;
  amount_max: string;
  /** "24, 36, 60" */
  term_months: string;
  origination_fee_min_pct: string;
  origination_fee_max_pct: string;
}

export interface CcFormValues {
  purchase_apr_min: string;
  purchase_apr_max: string;
  purchase_apr_variable: boolean;
  /** '' = no intro offer. */
  intro_apr: string;
  intro_months: string;
  balance_transfer_fee_pct: string;
  annual_fee: string;
  issuing_bank: string;
}

const DECIMAL = /^\d{1,9}(\.\d{1,4})?$/;

function decimal(check: (n: number) => boolean, format: string, range: string) {
  return z
    .string()
    .trim()
    .regex(DECIMAL, format)
    .refine((s) => !DECIMAL.test(s) || check(Number(s)), range);
}

// Backend core.domain: Apr (0, 100), Percent [0, 100), PositiveMoney > 0, Money >= 0. Each kind says what it
// wants in its own terms: a rate as a percent, an amount in dollars.
const apr = decimal(
  (n) => n > 0 && n < 100,
  'Enter the APR as a number, e.g. 7.49.',
  'Enter an APR above 0% and below 100%.',
);
const percent = decimal(
  (n) => n >= 0 && n < 100,
  'Enter a percentage as a number, e.g. 5.',
  'Enter a percentage from 0% to below 100%.',
);
const positiveMoney = decimal(
  (n) => n > 0,
  'Enter a dollar amount, e.g. 10000.',
  'Enter an amount above $0.',
);
const money = decimal((n) => n >= 0, 'Enter a dollar amount, e.g. 95.', 'Enter an amount of $0 or more.');

const MONTHS_MESSAGE = 'List loan terms in whole months, e.g. 24, 36, 60.';

function parseMonths(value: string): number[] | null {
  const parts = value.split(/[\s,]+/).filter((p) => p !== '');
  if (parts.length === 0 || parts.some((p) => !/^\d{1,3}$/.test(p) || Number(p) === 0)) return null;
  return [...new Set(parts.map(Number))].sort((a, b) => a - b);
}

/** min > max is an error on both fields, so it shows on whichever the lead just edited. */
function ordered(
  ctx: z.RefinementCtx,
  value: { min: string; max: string },
  paths: { min: string; max: string },
  label: string,
): void {
  if (DECIMAL.test(value.min) && DECIMAL.test(value.max) && Number(value.min) > Number(value.max)) {
    const again = label.startsWith('APR') ? label : label.charAt(0).toLowerCase() + label.slice(1);
    ctx.addIssue({
      code: 'custom',
      path: [paths.max],
      message: `${label} max must be at least ${again} min.`,
    });
    ctx.addIssue({
      code: 'custom',
      path: [paths.min],
      message: `${label} min must be at most ${again} max.`,
    });
  }
}

export const plFormSchema = z
  .object({
    apr_min: apr,
    apr_max: apr,
    amount_min: positiveMoney,
    amount_max: positiveMoney,
    term_months: z.string().refine((s) => parseMonths(s) !== null, MONTHS_MESSAGE),
    origination_fee_min_pct: percent,
    origination_fee_max_pct: percent,
  })
  .superRefine((v, ctx) => {
    ordered(ctx, { min: v.apr_min, max: v.apr_max }, { min: 'apr_min', max: 'apr_max' }, 'APR');
    ordered(
      ctx,
      { min: v.amount_min, max: v.amount_max },
      { min: 'amount_min', max: 'amount_max' },
      'Amount',
    );
    ordered(
      ctx,
      { min: v.origination_fee_min_pct, max: v.origination_fee_max_pct },
      { min: 'origination_fee_min_pct', max: 'origination_fee_max_pct' },
      'Origination fee',
    );
  });

const optionalPercent = z.union([z.literal(''), percent]);
const optionalMonths = z
  .string()
  .trim()
  .refine((s) => s === '' || (/^\d{1,3}$/.test(s) && Number(s) > 0), 'Enter whole months above 0.');

export const ccFormSchema = z
  .object({
    purchase_apr_min: apr,
    purchase_apr_max: apr,
    purchase_apr_variable: z.boolean(),
    intro_apr: optionalPercent,
    intro_months: optionalMonths,
    balance_transfer_fee_pct: percent,
    annual_fee: money,
    issuing_bank: z.string().trim().min(1, 'Name the issuing bank.').max(200),
  })
  .superRefine((v, ctx) => {
    ordered(
      ctx,
      { min: v.purchase_apr_min, max: v.purchase_apr_max },
      { min: 'purchase_apr_min', max: 'purchase_apr_max' },
      'Purchase APR',
    );
    const hasApr = v.intro_apr.trim() !== '';
    const hasMonths = v.intro_months.trim() !== '';
    if (hasApr && !hasMonths) {
      ctx.addIssue({
        code: 'custom',
        path: ['intro_months'],
        message: 'Set the intro period with the intro APR, or clear both.',
      });
    }
    if (hasMonths && !hasApr) {
      ctx.addIssue({
        code: 'custom',
        path: ['intro_apr'],
        message: 'Set the intro APR with the intro period, or clear both.',
      });
    }
  });

export const EMPTY_PL_FORM: PlFormValues = {
  apr_min: '',
  apr_max: '',
  amount_min: '',
  amount_max: '',
  term_months: '',
  origination_fee_min_pct: '',
  origination_fee_max_pct: '',
};

export const EMPTY_CC_FORM: CcFormValues = {
  purchase_apr_min: '',
  purchase_apr_max: '',
  purchase_apr_variable: true,
  intro_apr: '',
  intro_months: '',
  balance_transfer_fee_pct: '',
  annual_fee: '',
  issuing_bank: '',
};

export function plFormFrom(values: PersonalLoanTerms | undefined): PlFormValues {
  if (values === undefined) return EMPTY_PL_FORM;
  return {
    apr_min: values.apr_min,
    apr_max: values.apr_max,
    amount_min: values.amount_min,
    amount_max: values.amount_max,
    term_months: values.term_months.join(', '),
    origination_fee_min_pct: values.origination_fee_min_pct,
    origination_fee_max_pct: values.origination_fee_max_pct,
  };
}

export function ccFormFrom(values: CreditCardTerms | undefined): CcFormValues {
  if (values === undefined) return EMPTY_CC_FORM;
  return {
    purchase_apr_min: values.purchase_apr_min,
    purchase_apr_max: values.purchase_apr_max,
    purchase_apr_variable: values.purchase_apr_variable ?? true,
    intro_apr: values.intro_apr ?? '',
    intro_months:
      values.intro_months === null || values.intro_months === undefined ? '' : String(values.intro_months),
    balance_transfer_fee_pct: values.balance_transfer_fee_pct,
    annual_fee: values.annual_fee,
    issuing_bank: values.issuing_bank,
  };
}

/** The API body for valid form values; null while the form is invalid. */
export function plValuesFrom(form: PlFormValues): PersonalLoanTerms | null {
  const parsed = plFormSchema.safeParse(form);
  if (!parsed.success) return null;
  const v = parsed.data;
  return {
    product: 'personal_loan',
    apr_min: v.apr_min,
    apr_max: v.apr_max,
    amount_min: v.amount_min,
    amount_max: v.amount_max,
    term_months: parseMonths(v.term_months) ?? [],
    origination_fee_min_pct: v.origination_fee_min_pct,
    origination_fee_max_pct: v.origination_fee_max_pct,
  };
}

export function ccValuesFrom(form: CcFormValues): CreditCardTerms | null {
  const parsed = ccFormSchema.safeParse(form);
  if (!parsed.success) return null;
  const v = parsed.data;
  const intro = v.intro_apr.trim() !== '';
  return {
    product: 'credit_card',
    purchase_apr_min: v.purchase_apr_min,
    purchase_apr_max: v.purchase_apr_max,
    purchase_apr_variable: v.purchase_apr_variable,
    intro_apr: intro ? v.intro_apr.trim() : null,
    intro_months: intro ? Number(v.intro_months) : null,
    balance_transfer_fee_pct: v.balance_transfer_fee_pct,
    annual_fee: v.annual_fee,
    issuing_bank: v.issuing_bank.trim(),
  };
}

// ---- Comparing versions ------------------------------------------------------------------------------

function canonical(values: TermsValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const def of fieldsFor(values.product ?? 'personal_loan')) {
    const raw: unknown = (values as unknown as Record<string, unknown>)[def.key];
    if (def.kind === 'variable') out[def.key] = raw ?? true;
    else if (raw === undefined || raw === null || raw === '') out[def.key] = null;
    else if (typeof raw === 'string' && def.kind !== 'text') out[def.key] = normalizeDecimal(raw);
    else out[def.key] = raw;
  }
  return out;
}

/** A stable key for a set of values: equal Decimals give equal keys. */
export function termsKey(values: TermsValues): string {
  return JSON.stringify([values.product, canonical(values)]);
}

/** The values a key was made from, canonicalized (equal Decimals, so the backend sees the same terms). */
export function valuesFromKey(key: string): TermsValues {
  const [product, values] = JSON.parse(key) as [TermsProduct, Record<string, unknown>];
  return { product, ...values } as unknown as TermsValues;
}

/** The backend's "nothing changed" (`previous.typed_values == data.values`). */
export function sameTerms(a: TermsValues, b: TermsValues): boolean {
  return termsKey(a) === termsKey(b);
}

function canonicalInput(kind: FieldKind, value: string | boolean): string {
  if (typeof value === 'boolean') return String(value);
  if (kind === 'months_list') return (parseMonths(value) ?? [value.trim()]).join(',');
  if (kind === 'text') return value.trim();
  return normalizeDecimal(value);
}

/** Whether one form input differs from the version in effect (marks the row while editing). */
export function inputChanged(kind: FieldKind, value: string | boolean, base: string | boolean): boolean {
  return canonicalInput(kind, value) !== canonicalInput(kind, base);
}

export interface TermsChange {
  field: string;
  label: string;
  from: string;
  to: string;
}

/** Field by field, what differs from `before` to `after`, in form order. */
export function termsChanges(before: TermsValues, after: TermsValues): TermsChange[] {
  const a = canonical(before);
  const b = canonical(after);
  return fieldsFor(after.product ?? 'personal_loan')
    .filter((def) => JSON.stringify(a[def.key]) !== JSON.stringify(b[def.key]))
    .map((def) => ({
      field: def.key,
      label: def.label,
      from: formatTermsValue(def.kind, a[def.key]),
      to: formatTermsValue(def.kind, b[def.key]),
    }));
}
