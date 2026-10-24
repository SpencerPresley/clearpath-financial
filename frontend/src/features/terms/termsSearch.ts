/*
 * The Offer terms URL: which product's terms are open. A stale or hand-edited value falls back to personal loan
 * rather than throwing (the queue's `.catch()` rule).
 */
import { z } from 'zod';

export const TERMS_TABS = ['personal_loan', 'credit_card', 'mortgage_prequal'] as const;
export type TermsTab = (typeof TERMS_TABS)[number];

export const termsSearchSchema = z.object({
  product: z.enum(TERMS_TABS).optional().catch(undefined),
});

export type TermsSearch = z.infer<typeof termsSearchSchema>;
