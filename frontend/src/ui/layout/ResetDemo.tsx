import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { useGetDemoReset, useResetDemo } from '../../api/generated/admin/admin';
import { Button } from '../Button';
import { ModalDialog } from '../Dialog';
import { apiErrorMessage } from '../forms/apiErrors';
import { showToast } from '../toast';

const POLL_MS = 1000;

/**
 * Admin-only "Reset demo" confirmation: start the job, poll it, then refetch everything. The backend runs the
 * reset as a background job (it can outlast a request) and keeps people and sessions, so the admin stays signed
 * in. Rendered outside the account popover so closing the popover doesn't unmount a running reset.
 */
export function ResetDemoDialog({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
}) {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const start = useResetDemo();
  const job = useGetDemoReset(jobId ?? 0, {
    query: {
      enabled: jobId !== null,
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        return status === 'done' || status === 'failed' ? false : POLL_MS;
      },
    },
  });
  const status = jobId === null ? null : (job.data?.status ?? 'queued');
  const running = start.isPending || status === 'queued' || status === 'running';
  const finished = useRef<number | null>(null);

  useEffect(() => {
    if (jobId === null || status !== 'done' || finished.current === jobId) return;
    finished.current = jobId;
    onOpenChange(false);
    setJobId(null);
    showToast({ title: 'Demo reset', description: `${String(job.data?.seeded_items ?? 0)} items seeded.` });
    void qc.invalidateQueries();
  }, [jobId, status, job.data?.seeded_items, qc, onOpenChange]);

  const confirm = () => {
    start.mutate(undefined, {
      onSuccess: (started) => {
        setJobId(started.id);
      },
    });
  };

  return (
    <ModalDialog
      title="Reset the demo?"
      role="alertdialog"
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (running) return;
        if (!open) setJobId(null);
        onOpenChange(open);
      }}
    >
      <p>
        Replaces every item, partner, offer-terms version, import, and notification with the seeded demo data.
        People and sign-ins stay. Takes up to a minute.
      </p>
      {status === 'failed' && (
        <p role="alert" className="app-field-error">
          {job.data?.error}
        </p>
      )}
      {start.isError && (
        <p role="alert" className="app-field-error">
          {apiErrorMessage(start.error)}
        </p>
      )}
      <div className="app-dialog-actions">
        <Button
          variant="ghost"
          isDisabled={running}
          onPress={() => {
            setJobId(null);
            onOpenChange(false);
          }}
        >
          Cancel
        </Button>
        <Button variant="danger" icon="action.reset_demo" isDisabled={running} onPress={confirm}>
          {running ? 'Resetting…' : 'Reset demo'}
        </Button>
      </div>
    </ModalDialog>
  );
}
