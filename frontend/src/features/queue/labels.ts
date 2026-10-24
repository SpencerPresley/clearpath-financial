/* Display copy for queue enums (spec §5.4: short, domain-native, one term per concept). */
import type { Market, Product } from '../../api/generated/model';
import { CHANNEL_LABELS, OUTCOME_LABELS, REOPEN_REASON_LABELS } from '../../ui/labels';

/** Shorter than ui/labels' "Mortgage prequalification": the queue's product column is dense. */
export const PRODUCT_LABEL: Record<Product, string> = {
  personal_loan: 'Personal loan',
  credit_card: 'Credit card',
  mortgage_prequal: 'Mortgage prequal',
};

export const CHANNEL_LABEL = CHANNEL_LABELS;

/** The one map every screen uses ("Offer terms changed", "Live copy changed"). */
export const REOPEN_REASON_LABEL = REOPEN_REASON_LABELS;

export const OUTCOME_LABEL = OUTCOME_LABELS;

export function roundLabel(round: number): string {
  return `R${String(round)}`;
}

export const MARKET_LABEL: Record<Market, string> = {
  national: 'National',
  CA: 'CA',
};
