/*
 * What table cells need from the page without being re-created per render: a shared clock, and (Task 4) the
 * inline-edit permissions and actions. Columns are module constants, so this travels by context.
 */
import { createContext, use } from 'react';

import type { ItemRowOut, ItemUpdateIn } from '../../api/generated/model';

export interface QueueCellContextValue {
  /** One reference time for every age in the list; defaults to render time. */
  now?: Date;
  /** Inline-edit controls are tab stops only in the active row, so Tab doesn't walk every row's buttons. */
  activeId?: number | null;
  canEditRisk: (row: ItemRowOut) => boolean;
  canEditTags: (row: ItemRowOut) => boolean;
  canEditNotes: (row: ItemRowOut) => boolean;
  save: (row: ItemRowOut, patch: ItemUpdateIn) => void;
  /** Take an unassigned submitted item (claim) or hand one off (assign); see useAssignment.ts. */
  canClaim: (row: ItemRowOut) => boolean;
  canAssign: (row: ItemRowOut) => boolean;
  claim: (row: ItemRowOut) => void;
  assign: (row: ItemRowOut, assigneeId: number | null, name: string) => void;
}

const never = () => false;

export const READ_ONLY_CELLS: QueueCellContextValue = {
  canEditRisk: never,
  canEditTags: never,
  canEditNotes: never,
  save: () => undefined,
  canClaim: never,
  canAssign: never,
  claim: () => undefined,
  assign: () => undefined,
};

export const QueueCellContext = createContext<QueueCellContextValue>(READ_ONLY_CELLS);

export function useQueueCell(): QueueCellContextValue {
  return use(QueueCellContext);
}
