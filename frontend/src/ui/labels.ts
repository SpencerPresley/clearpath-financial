/*
 * Display labels for API enums (spec §5.4: one term per concept). Keyed by the generated enum types so a
 * new backend value fails typecheck here instead of rendering a raw slug.
 */
import type {
  AttachmentKind,
  Channel,
  DecisionOutcome,
  Market,
  Product,
  ReopenReason,
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

/** Channels that require a partner (backend core.domain.PARTNER_CHANNELS). */
export const PARTNER_CHANNELS: readonly Channel[] = ['affiliate_page'];

/** "1 finding" / "2 findings". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

/** "Oct 24, 2026". Dates from the API are ISO strings; date-only strings are read as local dates. */
export function formatDate(value: string): string {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** "12.4 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
