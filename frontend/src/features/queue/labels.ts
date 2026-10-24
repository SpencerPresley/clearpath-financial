/* Display copy for queue enums (spec §5.4: short, domain-native, one term per concept). */
import type { Channel, DecisionOutcome, Market, Product, ReopenReason } from '../../api/generated/model';

export const PRODUCT_LABEL: Record<Product, string> = {
  personal_loan: 'Personal loan',
  credit_card: 'Credit card',
  mortgage_prequal: 'Mortgage prequal',
};

export const CHANNEL_LABEL: Record<Channel, string> = {
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

export const REOPEN_REASON_LABEL: Record<ReopenReason, string> = {
  terms_changed: 'Terms changed',
  approval_expired: 'Approval expired',
  drift_detected: 'Drift detected',
};

export const OUTCOME_LABEL: Record<DecisionOutcome, string> = {
  approved: 'Approved',
  approved_with_edits: 'Approved with edits',
  changes_requested: 'Changes requested',
  rejected: 'Rejected',
};

export function roundLabel(round: number): string {
  return `R${String(round)}`;
}

export const MARKET_LABEL: Record<Market, string> = {
  national: 'National',
  CA: 'CA',
};
