/*
 * Partners URLs: the list's filters and the detail's tab. Every field is `.catch()`-guarded, so a stale or
 * hand-edited URL drops the bad field instead of throwing (the queue's rule).
 */
import { z } from 'zod';

import { PartnerStatus } from '../../api/generated/model';

export const partnersSearchSchema = z.object({
  status: z.enum(Object.values(PartnerStatus)).optional().catch(undefined),
  q: z.string().max(200).optional().catch(undefined),
});
export type PartnersSearch = z.infer<typeof partnersSearchSchema>;

export const PARTNER_TABS = ['items', 'findings', 'repeat'] as const;
export type PartnerTab = (typeof PARTNER_TABS)[number];

export const partnerSearchSchema = z.object({
  tab: z.enum(PARTNER_TABS).optional().catch(undefined),
  /** Findings history narrowed to one rule (a repeat issue's link). */
  rule: z.string().max(200).optional().catch(undefined),
});
export type PartnerSearch = z.infer<typeof partnerSearchSchema>;
