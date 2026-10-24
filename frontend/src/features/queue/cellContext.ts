/*
 * What table cells need from the page without being re-created per render: a shared clock, and (Task 4) the
 * inline-edit permissions and save function. Columns are module constants, so this travels by context.
 */
import { createContext, use } from 'react';

import type { ItemRowOut, ItemUpdateIn } from '../../api/generated/model';

export interface QueueCellContextValue {
  /** One reference time for every age in the list; defaults to render time. */
  now?: Date;
  canEditRisk: (row: ItemRowOut) => boolean;
  canEditTags: (row: ItemRowOut) => boolean;
  save: (row: ItemRowOut, patch: ItemUpdateIn) => void;
}

const never = () => false;

export const READ_ONLY_CELLS: QueueCellContextValue = {
  canEditRisk: never,
  canEditTags: never,
  save: () => undefined,
};

export const QueueCellContext = createContext<QueueCellContextValue>(READ_ONLY_CELLS);

export function useQueueCell(): QueueCellContextValue {
  return use(QueueCellContext);
}
