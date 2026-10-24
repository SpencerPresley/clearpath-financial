import { z } from 'zod';

export const REVIEW_TABS = ['findings', 'comments', 'details', 'evidence', 'history'] as const;
export type ReviewTab = (typeof REVIEW_TABS)[number];

/** Deep-linkable review state: the version shown, what it's compared with, and the open tab. */
export const reviewSearchSchema = z.object({
  v: z.coerce.number().int().positive().optional().catch(undefined),
  compare: z.coerce.number().int().positive().optional().catch(undefined),
  tab: z.enum(REVIEW_TABS).optional().catch(undefined),
});

export type ReviewSearch = z.infer<typeof reviewSearchSchema>;
