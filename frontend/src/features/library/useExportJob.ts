/*
 * One export job (an xlsx of a view, or an item's evidence pack): start it, poll GET /exports/{id} until it's
 * ready or failed, then hand back its download_url. The download is a plain link: the mutator parses non-JSON
 * bodies as text, which would corrupt an xlsx or zip, and a link keeps the browser's own download handling.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getGetExportQueryKey, useGetExport } from '../../api/generated/exports/exports';
import type { ExportOut } from '../../api/generated/model';
import { errorStatus } from '../../ui/errorMessage';
import { apiErrorMessage } from '../../ui/forms/apiErrors';

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

export interface StartOutcome {
  isPending: boolean;
  error: unknown;
}

/**
 * `start` is the caller's mutation (createExport or createEvidencePack); pass its pending flag and error, and
 * call `track(job)` from its onSuccess.
 */
export function useExportJob(mutation: StartOutcome) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const poll = useGetExport(jobId ?? 0, {
    query: {
      enabled: jobId !== null,
      refetchInterval: (query) => (inFlight(query.state.data) ? POLL_MS : false),
    },
  });

  const track = (job: ExportOut) => {
    queryClient.setQueryData(getGetExportQueryKey(job.id), job);
    setJobId(job.id);
  };
  const reset = () => {
    setJobId(null);
  };

  let state: ExportJobState;
  if (mutation.isPending) {
    state = { kind: 'starting' };
  } else if (jobId === null) {
    state =
      mutation.error === null || mutation.error === undefined
        ? { kind: 'idle' }
        : {
            kind: 'refused',
            message: apiErrorMessage(mutation.error),
            status: errorStatus(mutation.error),
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

  return { state, track, reset, refetch: () => void poll.refetch() };
}
