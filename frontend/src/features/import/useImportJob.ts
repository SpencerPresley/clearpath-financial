/*
 * The import job and its preview, kept in step with the server: the job polls while it's committing, and the
 * preview is refetched once commit finishes (it then reports what commit did, with each created item's id).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import {
  getGetImportPreviewQueryKey,
  getGetImportQueryKey,
  getListImportsQueryKey,
  useCommitImport,
  useGetImport,
  useGetImportPreview,
  useSetImportMapping,
} from '../../api/generated/imports/imports';
import type { ImportJobOut, ImportMappingIn, ImportPreviewOut } from '../../api/generated/model';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { mappingErrors, NO_ERRORS } from './mappingErrors';

export const IMPORT_POLL_MS = 1000;

export function useImportJob(jobId: number) {
  const queryClient = useQueryClient();
  const job = useGetImport(jobId, {
    query: { refetchInterval: (q) => (q.state.data?.status === 'committing' ? IMPORT_POLL_MS : false) },
  });
  const status = job.data?.status;
  const preview = useGetImportPreview(jobId, {
    query: { enabled: status !== undefined && status !== 'committing' },
  });

  // Commit finished while we watched: the stored preview now says what commit did.
  const previous = useRef(status);
  useEffect(() => {
    if (previous.current === 'committing' && status !== 'committing') {
      void queryClient.invalidateQueries({ queryKey: getGetImportPreviewQueryKey(jobId) });
      void queryClient.invalidateQueries({ queryKey: getListImportsQueryKey() });
    }
    previous.current = status;
  }, [status, jobId, queryClient]);

  return { job, preview };
}

export function useSaveMapping(jobId: number, onSaved: (preview: ImportPreviewOut) => void) {
  const queryClient = useQueryClient();
  const mutation = useSetImportMapping({
    mutation: {
      onSuccess: (preview) => {
        queryClient.setQueryData(getGetImportPreviewQueryKey(jobId), preview);
        void queryClient.invalidateQueries({ queryKey: getGetImportQueryKey(jobId) });
        onSaved(preview);
      },
    },
  });
  return {
    isPending: mutation.isPending,
    errors: mutation.isError ? mappingErrors(mutation.error) : NO_ERRORS,
    mutate: (data: ImportMappingIn) => {
      mutation.mutate({ jobId, data });
    },
  };
}

/** `onStarted` runs once the server accepts the commit (the view drops its chosen step, so it ends on Done). */
export function useCommit(jobId: number, onStarted: () => void) {
  const queryClient = useQueryClient();
  const mutation = useCommitImport({
    mutation: {
      onSuccess: (job: ImportJobOut) => {
        onStarted();
        queryClient.setQueryData(getGetImportQueryKey(jobId), job);
        void queryClient.invalidateQueries({ queryKey: getGetImportPreviewQueryKey(jobId) });
      },
    },
  });
  return {
    isPending: mutation.isPending,
    error: mutation.isError ? apiErrorMessage(mutation.error) : null,
    commit: () => {
      mutation.mutate({ jobId, data: { skip_rows_with_problems: true } });
    },
  };
}
