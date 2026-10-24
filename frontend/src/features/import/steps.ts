/*
 * Where an import is: derived from the job's status and its preview, not kept in local state, so a reload, a
 * second tab, or coming back from Recent imports all land on the same step.
 *
 *   uploaded                 -> columns (the guesses need a look)
 *   mapped / failed          -> values while anything is unmapped, else preview
 *   committing               -> commit (progress, polling)
 *   committed                -> summary
 *
 * Before commit the admin may step back to an earlier editable step (the URL's `step`).
 */
import type { ImportJobOut, ImportPreviewOut } from '../../api/generated/model';
import type { EditableStep } from './search';

export type ImportStep = EditableStep | 'commit' | 'summary';

export const STEP_ORDER: readonly { id: ImportStep; label: string }[] = [
  { id: 'columns', label: 'Columns' },
  { id: 'values', label: 'Values' },
  { id: 'preview', label: 'Preview' },
  { id: 'commit', label: 'Import' },
  { id: 'summary', label: 'Done' },
];

export function currentStep(
  job: ImportJobOut,
  preview: ImportPreviewOut | undefined,
  requested: EditableStep | undefined,
): ImportStep {
  if (job.status === 'committing') return 'commit';
  if (job.status === 'committed') return 'summary';
  if (requested !== undefined) return requested;
  if (job.status === 'uploaded') return 'columns';
  return (preview?.unmapped.length ?? 0) > 0 ? 'values' : 'preview';
}

export function isEditable(job: ImportJobOut): boolean {
  return job.status === 'uploaded' || job.status === 'mapped' || job.status === 'failed';
}
