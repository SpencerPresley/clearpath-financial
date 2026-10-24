import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getDemoReset, useResetDemo } from '../../api/generated/admin/admin';
import type { DemoResetOut } from '../../api/generated/model';
import { Button } from '../Button';
import { ModalDialog } from '../Dialog';
import { apiErrorMessage } from '../forms/apiErrors';
import { showToast } from '../toast';

export const RESET_POLL_MS = 1000;

const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

/**
 * Admin-only "Reset demo" confirmation: start the job, poll it, then refetch everything. The backend runs the
 * reset as a background job (it can outlast a request) and keeps people and sessions, so the admin stays signed
 * in. Rendered outside the account popover so closing the popover doesn't unmount a running reset; closing this
 * dialog only stops showing it, so polling continues and the outcome still arrives as a toast.
 */
export function ResetDemoDialog({
  isOpen,
  onOpenChange,
  onDone,
}: {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  /** After a reset finished: leave the screen (it may show deleted data). Default: refetch everything. */
  onDone?: () => Promise<void>;
}) {
  const qc = useQueryClient();
  const start = useResetDemo();
  const [job, setJob] = useState<DemoResetOut | null>(null);
  const [pollError, setPollError] = useState<unknown>(null);
  const running = start.isPending || job?.status === 'queued' || job?.status === 'running';

  const watch = async (first: DemoResetOut) => {
    let current = first;
    while (current.status === 'queued' || current.status === 'running') {
      await wait(RESET_POLL_MS);
      try {
        current = await getDemoReset(first.id);
      } catch (error) {
        // Transient (a dev server restart, a dropped connection): keep watching; the job runs regardless.
        setPollError(error);
        continue;
      }
      setPollError(null);
      setJob(current);
    }
    if (current.status === 'done') {
      setJob(null);
      onOpenChange(false);
      showToast({ title: 'Demo reset', description: `${String(current.seeded_items)} items seeded.` });
      await (onDone === undefined ? qc.invalidateQueries() : onDone());
    } else {
      showToast({ title: "The demo reset didn't finish", description: current.error, tone: 'error' });
    }
  };

  const confirm = () => {
    setJob(null);
    start.mutate(undefined, {
      onSuccess: (started) => {
        setJob(started);
        void watch(started);
      },
    });
  };

  const close = () => {
    if (!running) {
      setJob(null);
      start.reset();
    }
    onOpenChange(false);
  };

  return (
    <ModalDialog
      title="Reset the demo?"
      role="alertdialog"
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (open) onOpenChange(true);
        else close();
      }}
    >
      <p>
        Replaces every item, partner, offer-terms version, import, and notification with the seeded demo data.
        People and sign-ins stay. Takes up to a minute.
      </p>
      {running && job !== null && (
        <p>Resetting. You can close this; you&apos;ll get a notice when it&apos;s done.</p>
      )}
      {running && pollError !== null && (
        <p className="app-field-error">
          Can&apos;t check on the reset right now: {apiErrorMessage(pollError)}
        </p>
      )}
      {job?.status === 'failed' && (
        <p role="alert" className="app-field-error">
          {job.error}
        </p>
      )}
      {start.isError && (
        <p role="alert" className="app-field-error">
          {apiErrorMessage(start.error)}
        </p>
      )}
      <div className="app-dialog-actions">
        <Button variant="ghost" onPress={close}>
          {running ? 'Run in background' : 'Cancel'}
        </Button>
        <Button variant="danger" icon="action.reset_demo" isDisabled={running} onPress={confirm}>
          {running ? 'Resetting…' : 'Reset demo'}
        </Button>
      </div>
    </ModalDialog>
  );
}
