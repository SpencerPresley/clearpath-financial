/*
 * Export and evidence-pack jobs belong to the page, not to the control that started them: switching tabs or
 * filtering a row away unmounts the control, and the job (still running on the server) must be there when it
 * comes back. One record per key ('export', 'pack:<itemId>'), held by LibraryPage.
 */
import { createContext, use, useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type { ExportIn } from '../../api/generated/model';

export interface JobRecord {
  /** starting: the POST is in flight; tracking: polling `jobId`; refused: the POST was answered with an error. */
  phase: 'starting' | 'tracking' | 'refused';
  jobId?: number;
  message?: string;
  httpStatus?: number;
  /** What was asked for (exports), so Retry re-sends that request rather than the filters on screen now. */
  request?: ExportIn;
}

interface Store {
  records: Readonly<Record<string, JobRecord>>;
  set: (key: string, record: JobRecord | undefined) => void;
}

const ExportJobsContext = createContext<Store | null>(null);

export function ExportJobsProvider({ children }: { children: ReactNode }) {
  const [records, setRecords] = useState<Record<string, JobRecord>>({});
  const set = useCallback((key: string, record: JobRecord | undefined) => {
    setRecords((all) => {
      if (record !== undefined) return { ...all, [key]: record };
      return Object.fromEntries(Object.entries(all).filter(([k]) => k !== key));
    });
  }, []);
  const store = useMemo(() => ({ records, set }), [records, set]);
  return <ExportJobsContext value={store}>{children}</ExportJobsContext>;
}

export function useExportJobs(): Store {
  const store = use(ExportJobsContext);
  if (store === null) throw new Error('useExportJobs needs an ExportJobsProvider (LibraryPage provides it).');
  return store;
}

export const EXPORT_KEY = 'export';
export const packKey = (itemId: number) => `pack:${String(itemId)}`;
