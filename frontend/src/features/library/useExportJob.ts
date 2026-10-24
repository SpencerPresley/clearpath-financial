/*
 * One export job (an xlsx of a view, or an item's evidence pack), read from the page's job store (exportJobs.tsx):
 * poll GET /exports/{id} until it's ready or failed, then hand back its download_url. The download is a plain
 * link: the mutator parses non-JSON bodies as text, which would corrupt an xlsx or zip, and a link keeps the
 * browser's own download handling.
 */
import { useQueryClient } from '@tanstack/react-query';

import { getGetExportQueryKey, useGetExport } from '../../api/generated/exports/exports';
import type { ExportOut } from '../../api/generated/model';
import { errorStatus } from '../../ui/errorMessage';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { useExportJobs } from './exportJobs';
import type { JobRecord } from './exportJobs';

export const POLL_MS = 1000;

export type ExportJobState =
  | { kind: 'idle' }
  | { kind: 'starting' }
  | { kind: 'refused'; message: string; status: number | undefined }
  | { kind: 'running'; job: ExportOut | undefined }
  | { kind: 'ready'; job: ExportOut; url: string }
  | { kind: 'failed'; message: string }
  | { kind: 'lost'; message: string };

const inFlight = (job: ExportOut | undefined) =>
  job === undefined || job.status === 'pending' || job.status === 'running';

/** Callbacks for the starting mutation's own options (they run even if the control has unmounted meanwhile). */
export function useJobCallbacks() {
  const queryClient = useQueryClient();
  const { set } = useExportJobs();
  return {
    starting: (key: string, extra: Partial<JobRecord> = {}) => {
      set(key, { phase: 'starting', ...extra });
    },
    started: (key: string, job: ExportOut, extra: Partial<JobRecord> = {}) => {
      queryClient.setQueryData(getGetExportQueryKey(job.id), job);
      set(key, { phase: 'tracking', jobId: job.id, ...extra });
    },
    refused: (key: string, error: unknown, extra: Partial<JobRecord> = {}) => {
      set(key, {
        phase: 'refused',
        message: apiErrorMessage(error),
        httpStatus: errorStatus(error),
        ...extra,
      });
    },
    clear: (key: string) => {
      set(key, undefined);
    },
  };
}

export function useExportJob(key: string) {
  const { records } = useExportJobs();
  const record = records[key];
  const jobId = record?.phase === 'tracking' ? (record.jobId ?? null) : null;
  const poll = useGetExport(jobId ?? 0, {
    query: {
      enabled: jobId !== null,
      refetchInterval: (query) => (inFlight(query.state.data) ? POLL_MS : false),
    },
  });

  let state: ExportJobState;
  if (record === undefined) {
    state = { kind: 'idle' };
  } else if (record.phase === 'starting') {
    state = { kind: 'starting' };
  } else if (record.phase === 'refused') {
    state = {
      kind: 'refused',
      message: record.message ?? 'The request was refused.',
      status: record.httpStatus,
    };
  } else if (poll.isError && poll.data === undefined) {
    state = { kind: 'lost', message: apiErrorMessage(poll.error) };
  } else {
    const job = poll.data;
    if (job?.status === 'ready' && job.download_url !== null) {
      state = { kind: 'ready', job, url: job.download_url };
    } else if (job?.status === 'failed') {
      state = { kind: 'failed', message: job.error ?? 'The export failed. Try again.' };
    } else {
      state = { kind: 'running', job };
    }
  }
  return { state, record };
}
