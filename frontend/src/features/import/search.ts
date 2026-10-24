/*
 * The import screen's URL: which job, and which editable step the admin chose. The step otherwise follows the
 * job's server state (steps.ts), so a refresh lands where the import actually is.
 */
import { z } from 'zod';

export const EDITABLE_STEPS = ['columns', 'values', 'preview'] as const;
export type EditableStep = (typeof EDITABLE_STEPS)[number];

export const importSearchSchema = z.object({
  job: z.number().int().positive().optional().catch(undefined),
  step: z.enum(EDITABLE_STEPS).optional().catch(undefined),
});

export type ImportSearch = z.output<typeof importSearchSchema>;
