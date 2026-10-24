/*
 * Display labels for API enums (spec §5.4: one term per concept). Keyed by the generated enum types so a
 * new backend value fails typecheck here instead of rendering a raw slug.
 */
import type {
  AttachmentKind,
  Channel,
  DecisionOutcome,
  DriftResult,
  FindingState,
  LlmFailureCode,
  Market,
  PartnerStatus,
  PartnerType,
  Product,
  ReopenReason,
  RiskTier,
  TermsField,
  VersionOrigin,
} from '../api/generated/model';

export const PRODUCT_LABELS: Record<Product, string> = {
  personal_loan: 'Personal loan',
  credit_card: 'Credit card',
  mortgage_prequal: 'Mortgage prequalification',
};

export const CHANNEL_LABELS: Record<Channel, string> = {
  email: 'Email',
  sms: 'SMS',
  paid_social: 'Paid social',
  paid_search: 'Paid search',
  display: 'Display',
  direct_mail: 'Direct mail',
  landing_page: 'Landing page',
  affiliate_page: 'Affiliate page',
  call_script: 'Call script',
};

export const MARKET_LABELS: Record<Market, string> = {
  national: 'National',
  CA: 'California',
};

export const ATTACHMENT_KIND_LABELS: Record<AttachmentKind, string> = {
  creative: 'Mockup',
  substantiation: 'Substantiation',
  agreement: 'Agreement',
  rate_sheet: 'Rate sheet',
  prescreen_criteria: 'Prescreen criteria',
  consent_record: 'Consent record',
  screenshot: 'Screenshot',
  other: 'Other',
};

export const REOPEN_REASON_LABELS: Record<ReopenReason, string> = {
  terms_changed: 'Offer terms changed',
  approval_expired: 'Approval expired',
  drift_detected: 'Live copy changed',
};

export const ORIGIN_LABELS: Record<VersionOrigin, string> = {
  submission: 'Submission',
  reviewer_edit: 'Reviewer edit',
  fast_track: 'Fast-track',
};

export const OUTCOME_LABELS: Record<DecisionOutcome, string> = {
  approved: 'Approved',
  approved_with_edits: 'Approved with edits',
  changes_requested: 'Changes requested',
  rejected: 'Rejected',
};

export const PARTNER_TYPE_LABELS: Record<PartnerType, string> = {
  affiliate: 'Affiliate',
  lead_gen: 'Lead gen',
  marketplace: 'Marketplace',
  influencer: 'Influencer',
};

/** A partner's standing with ClearPath: an attribute, shown without a status color (spec §5.2). */
export const PARTNER_STATUS_LABELS: Record<PartnerStatus, string> = {
  active: 'Active',
  paused: 'Paused',
  terminated: 'Terminated',
};

export const FINDING_STATE_LABELS: Record<FindingState, string> = {
  open: 'Open',
  accepted: 'Accepted',
  dismissed: 'Dismissed',
};

/** Channels that require a partner (backend core.domain.PARTNER_CHANNELS). */
export const PARTNER_CHANNELS: readonly Channel[] = ['affiliate_page'];

/** "1 finding" / "2 findings". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

/*
 * Dates: every date the app shows goes through these, so one screen never says "2025-09-26" or
 * "10/22/2026, 2:40:00 PM" next to another's "Oct 22, 2026". Values from the API are ISO strings; a date-only
 * string ("2026-07-21") is that calendar day wherever the viewer is, not UTC midnight shifted a day back.
 */
const DATE_FORMAT = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' });
const DATE_TIME_FORMAT = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });
const DAY_MONTH_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const MONTH_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric' });

export type DateValue = string | Date | null | undefined;

function toDate(value: DateValue): Date | null {
  if (value === null || value === undefined || value === '') return null;
  const date =
    value instanceof Date
      ? value
      : /^\d{4}-\d{2}-\d{2}$/.test(value)
        ? new Date(`${value}T00:00:00`)
        : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function format(formatter: Intl.DateTimeFormat, value: DateValue): string {
  const date = toDate(value);
  return date === null ? '—' : formatter.format(date);
}

/** "Oct 24, 2026"; "—" when there's no date. */
export function formatDate(value: DateValue): string {
  return format(DATE_FORMAT, value);
}

/** "Oct 22, 2026, 2:40 PM": tooltips behind relative ages, sent times. */
export function formatDateTime(value: DateValue): string {
  return format(DATE_TIME_FORMAT, value);
}

/** "Oct 19": weekly chart ticks and same-year mentions where the year is plain from context. */
export function formatDayMonth(value: DateValue): string {
  return format(DAY_MONTH_FORMAT, value);
}

/** "Oct 2026": monthly chart ticks. */
export function formatMonth(value: DateValue): string {
  return format(MONTH_FORMAT, value);
}

/** "Oct 22, 2026, 2:40 PM": a moment, as tooltips and records show it (the same format as `formatDate` plus time). */
export function formatDateTime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
}

/** "12.4 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/*
 * Drift (product-spec "Drift monitoring"): one name everywhere (spec §5.4). The concept and the reopen reason are
 * "Live copy changed"; a check's result is Unchanged / Changed / Missing. The exports use the same words
 * (backend/exports/labels.py).
 */
export const DRIFT_CONCEPT_LABEL = REOPEN_REASON_LABELS.drift_detected;

export const DRIFT_RESULT_LABELS: Record<DriftResult, string> = {
  unchanged: 'Unchanged',
  modified: 'Changed',
  missing: 'Missing',
};

export const RISK_TIER_LABELS: Record<RiskTier, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

/** The Offer terms screen's field names (features/terms/termsForm.ts), for quotes and decision records. */
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

/**
 * Why an AI pre-review failed, in plain words (spec §5.4). The server's `llm_check_failure_reason` can carry
 * provider detail ("The model provider returned 529."), which means nothing to a compliance reviewer.
 */
export const LLM_FAILURE_LABELS: Record<LlmFailureCode, string> = {
  not_configured: 'AI review isn’t configured on this server.',
  provider_unavailable: 'The AI service was overloaded and didn’t answer after several tries.',
  provider_refused: 'The AI service refused the request.',
  invalid_output: 'The AI’s answer couldn’t be read.',
  stuck: 'The AI check stopped without finishing.',
  timeout: 'The AI check took too long and was stopped.',
  error: 'The AI check hit an unexpected error.',
};
