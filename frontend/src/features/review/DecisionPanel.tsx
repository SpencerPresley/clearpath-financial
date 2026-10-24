import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  getListDecisionsQueryKey,
  useBulkFastTrackApprove,
  usePullItem,
  useReaffirmApproval,
  useRecordDecision,
} from '../../api/generated/decisions/decisions';
import { getListFindingsQueryKey } from '../../api/generated/findings/findings';
import {
  getGetItemHistoryQueryKey,
  getGetItemQueryKey,
  getListPlacementsQueryKey,
  getListVersionsQueryKey,
  useListPlacements,
} from '../../api/generated/items/items';
import type { AttachmentOut, FindingOut, ItemDetailOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import type { ButtonVariant } from '../../ui/Button';
import { ModalDialog } from '../../ui/Dialog';
import { CheckboxField, TextAreaField } from '../../ui/forms/fields';
import { apiErrorBody, apiErrorMessage } from '../../ui/forms/apiErrors';
import type { IconKey } from '../../ui/icons';
import { ItemKey } from '../../ui/ItemKey';
import { ATTACHMENT_KIND_LABELS, formatDate } from '../../ui/labels';
import { showToast } from '../../ui/toast';
import { APPROVE_MODES, changesRequestedDraft } from './decisionModes';
import type { DecisionMode } from './decisionModes';
import type { DecisionGate } from './gate';

interface ModeCopy {
  title: (n: number, nextN: number) => string;
  submit: string;
  icon: IconKey;
  variant: ButtonVariant;
  reasonLabel: string;
  placeholder: string;
  done: string;
}

const MODES: Record<DecisionMode, ModeCopy> = {
  approved: {
    title: (n) => `Approve v${String(n)}`,
    submit: 'Approve',
    icon: 'action.approve',
    variant: 'primary',
    reasonLabel: 'Reason',
    placeholder: 'What you checked and why it can run',
    done: 'Approved',
  },
  approved_with_edits: {
    title: (_n, next) => `Approve with edits as v${String(next)}`,
    submit: 'Approve edited version',
    icon: 'action.approve',
    variant: 'primary',
    reasonLabel: 'Reason',
    placeholder: 'What you changed and why it can run',
    done: 'Approved with edits',
  },
  changes_requested: {
    title: (n) => `Request changes on v${String(n)}`,
    submit: 'Request changes',
    icon: 'action.request_changes',
    variant: 'primary',
    reasonLabel: 'Changes needed',
    placeholder: 'What the marketer needs to change',
    done: 'Changes requested',
  },
  rejected: {
    title: (n) => `Reject v${String(n)}`,
    submit: 'Reject…',
    icon: 'action.reject',
    variant: 'danger',
    reasonLabel: 'Reason',
    placeholder: 'Why this can’t run in any form',
    done: 'Rejected',
  },
  fast_track: {
    title: (n) => `Fast-track approve v${String(n)}`,
    submit: 'Fast-track approve',
    icon: 'action.approve',
    variant: 'primary',
    reasonLabel: 'Reason',
    placeholder: 'e.g. Only the offer-terms numbers changed',
    done: 'Fast-track approved',
  },
  reaffirm: {
    title: () => 'Reaffirm the approval',
    submit: 'Reaffirm',
    icon: 'action.approve',
    variant: 'primary',
    reasonLabel: 'Reason',
    placeholder: 'Why the approved version can keep running as is',
    done: 'Approval reaffirmed',
  },
  pull: {
    title: () => 'Pull live content',
    submit: 'Pull…',
    icon: 'action.pull',
    variant: 'danger',
    reasonLabel: 'Reason',
    placeholder: 'Why it has to come down',
    done: 'Takedown requested',
  },
};

export interface DecisionPanelProps {
  item: ItemDetailOut;
  mode: DecisionMode;
  gate: DecisionGate;
  findings: readonly FindingOut[];
  attachments: readonly AttachmentOut[];
  /**
   * Approve with edits: the reviewer's text (the panel posts it; the center pane edits it). Undefined when
   * re-approving a reviewer-edit version after triaging its new findings (the text is already v+1).
   */
  editedText?: string;
  onCancel: () => void;
  onDone: () => void;
  /** The server kept the reviewer's v+1 but it has new findings to triage first (409 findings_need_triage). */
  onNeedsTriage: (message: string) => void;
}

function LivePlacements({ itemId }: { itemId: number }) {
  const placements = useListPlacements(itemId);
  const live = (placements.data ?? []).filter((p) => p.is_live);
  if (placements.isPending) {
    return <p className="app-muted">Loading placements…</p>;
  }
  if (live.length === 0) {
    return <p className="app-muted">No live placements recorded. The item will be withdrawn.</p>;
  }
  return (
    <ul className="app-plain-list">
      {live.map((p) => (
        <li key={p.id}>
          {p.location} · since {formatDate(p.first_run)}
        </li>
      ))}
    </ul>
  );
}

/**
 * The inline form under the decision bar. Every decision needs a reason (spec §4.3). Reject and Pull ask
 * for confirmation in a dialog; nothing else does (spec §5.7).
 */
export function DecisionPanel({
  item,
  mode,
  gate,
  findings,
  attachments,
  editedText,
  onCancel,
  onDone,
  onNeedsTriage,
}: DecisionPanelProps) {
  const queryClient = useQueryClient();
  const copy = MODES[mode];
  const isApprove = APPROVE_MODES.includes(mode);
  const currentN = item.current_version_n ?? 0;
  const approvedN = item.latest_decision?.version_n ?? currentN;

  const [reason, setReason] = useState(() =>
    mode === 'changes_requested' ? changesRequestedDraft(findings) : '',
  );
  const [override, setOverride] = useState('');
  const [evidence, setEvidence] = useState<number[]>(() => attachments.map((a) => a.id));
  const [errors, setErrors] = useState<{ reason?: string; override?: string; form?: string }>({});
  const [confirming, setConfirming] = useState(false);

  const refresh = () => {
    for (const key of [
      getGetItemQueryKey(item.id),
      getListFindingsQueryKey(item.id),
      getListDecisionsQueryKey(item.id),
      getGetItemHistoryQueryKey(item.id),
      getListVersionsQueryKey(item.id),
      getListPlacementsQueryKey(item.id),
    ]) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  };
  const settle = (n: number) => {
    refresh();
    showToast({
      title: `${copy.done} · v${String(n)}`,
      description: <ItemKey value={item.key} copyable={false} />,
    });
    onDone();
  };
  const fail = (error: unknown) => {
    setConfirming(false);
    const code = apiErrorBody(error)?.code;
    // The item moved on under us (a new version, or new findings on the reviewer's edit): reload it.
    if (code === 'findings_need_triage' || code === 'stale_version') {
      refresh();
    }
    if (code === 'findings_need_triage') {
      onNeedsTriage(apiErrorMessage(error));
      return;
    }
    setErrors({ form: apiErrorMessage(error) });
  };

  const record = useRecordDecision({
    mutation: {
      onSuccess: (d) => {
        settle(d.version_n);
      },
      onError: fail,
    },
  });
  const fastTrack = useBulkFastTrackApprove({
    mutation: {
      onSuccess: (result) => {
        const skipped = result.skipped.find((s) => s.item_id === item.id);
        if (skipped !== undefined) {
          setErrors({ form: `Not fast-tracked: ${skipped.message}` });
          return;
        }
        settle(currentN);
      },
      onError: fail,
    },
  });
  const reaffirm = useReaffirmApproval({
    mutation: {
      onSuccess: (d) => {
        settle(d.version_n);
      },
      onError: fail,
    },
  });
  const pull = usePullItem({
    mutation: {
      onSuccess: () => {
        settle(approvedN);
      },
      onError: fail,
    },
  });
  const pending = record.isPending || fastTrack.isPending || reaffirm.isPending || pull.isPending;

  const reapprovingEdit = mode === 'approved_with_edits' && editedText === undefined;
  const noEdits =
    mode === 'approved_with_edits' &&
    !reapprovingEdit &&
    editedText === (item.current_version?.content_text ?? '');
  const actionGate = mode === 'approved_with_edits' ? gate.approveWithEdits : gate.approve;
  const blocked = isApprove && !actionGate.enabled;

  const send = () => {
    const trimmed = reason.trim();
    switch (mode) {
      case 'fast_track':
        fastTrack.mutate({ data: { item_ids: [item.id], reason: trimmed } });
        return;
      case 'reaffirm':
        reaffirm.mutate({ itemId: item.id, data: { reason: trimmed } });
        return;
      case 'pull':
        pull.mutate({ itemId: item.id, data: { reason: trimmed } });
        return;
      default:
        record.mutate({
          itemId: item.id,
          data: {
            outcome: mode,
            version_n: currentN,
            reason: trimmed,
            evidence_attachment_ids: isApprove ? evidence : [],
            llm_override_reason: isApprove && gate.overrideRequired ? override.trim() : null,
            // Re-approving a reviewer-edit version after triage posts no text (the text is already v+1).
            edited_content_text: mode === 'approved_with_edits' ? (editedText ?? null) : null,
          },
        });
    }
  };

  const submit = () => {
    const next: typeof errors = {};
    if (reason.trim() === '') next.reason = 'Give a reason; it goes on the decision record.';
    if (isApprove && gate.overrideRequired && override.trim() === '')
      next.override = 'Say why it’s safe to approve without the AI check.';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    if (mode === 'rejected' || mode === 'pull') {
      setConfirming(true);
      return;
    }
    send();
  };

  const nextN = currentN + 1;
  const titleN = mode === 'reaffirm' || mode === 'pull' ? approvedN : currentN;

  return (
    <section className="app-decision-panel" aria-labelledby="decision-panel-title" data-mode={mode}>
      <form
        className="app-decision-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
      >
        <h2 id="decision-panel-title" className="app-decision-panel-title">
          {reapprovingEdit ? `Approve your edited v${String(currentN)}` : copy.title(titleN, nextN)}
        </h2>
        <div className="app-decision-fields">
          <TextAreaField
            label={copy.reasonLabel}
            value={reason}
            onChange={(value) => {
              setReason(value);
              setErrors((e) => ({ ...e, reason: undefined }));
            }}
            placeholder={copy.placeholder}
            errorMessage={errors.reason}
            rows={mode === 'changes_requested' ? 4 : 2}
            autoFocus={mode !== 'approved_with_edits'}
            isRequired
            description={
              mode === 'changes_requested'
                ? 'Starts from the accepted findings. The marketer sees this.'
                : undefined
            }
          />
          {isApprove && gate.overrideRequired && (
            <TextAreaField
              label="Override reason"
              description="The AI check failed. This is recorded on the decision."
              value={override}
              onChange={(value) => {
                setOverride(value);
                setErrors((e) => ({ ...e, override: undefined }));
              }}
              errorMessage={errors.override}
              rows={2}
              isRequired
            />
          )}
          {mode === 'pull' && (
            <div className="app-field">
              <span className="app-field-label">Live placements to take down</span>
              <LivePlacements itemId={item.id} />
            </div>
          )}
          {isApprove && attachments.length > 0 && (
            <fieldset className="app-field">
              <legend className="app-field-label">Evidence relied on</legend>
              <div className="app-checkbox-stack">
                {attachments.map((a) => (
                  <CheckboxField
                    key={a.id}
                    isSelected={evidence.includes(a.id)}
                    onChange={(selected) => {
                      setEvidence((ids) => (selected ? [...ids, a.id] : ids.filter((id) => id !== a.id)));
                    }}
                  >
                    {a.original_name} <span className="app-muted">· {ATTACHMENT_KIND_LABELS[a.kind]}</span>
                  </CheckboxField>
                ))}
              </div>
            </fieldset>
          )}
        </div>
        <div className="app-decision-actions">
          <Button
            type="submit"
            variant={copy.variant}
            icon={copy.icon}
            isDisabled={pending || blocked || noEdits}
          >
            {pending ? 'Saving…' : copy.submit}
          </Button>
          <Button variant="ghost" onPress={onCancel}>
            Cancel
          </Button>
          {blocked && <span className="app-gate-note">{actionGate.blockers.join(' · ')}</span>}
          {!blocked && noEdits && <span className="app-gate-note">No edits yet</span>}
          {errors.form !== undefined && (
            <span className="app-field-error" role="alert">
              {errors.form}
            </span>
          )}
        </div>
      </form>
      <ModalDialog
        title={mode === 'pull' ? `Pull ${item.key}?` : `Reject ${item.key}?`}
        role="alertdialog"
        isOpen={confirming}
        onOpenChange={setConfirming}
      >
        <p>
          {mode === 'pull'
            ? 'Requests a takedown of every live placement and withdraws the item. The marketer can start a new round later.'
            : 'Rejecting ends review of this item. The marketer would have to submit it again as a new item.'}
        </p>
        <div className="app-dialog-actions">
          <Button
            variant="ghost"
            onPress={() => {
              setConfirming(false);
            }}
          >
            Keep reviewing
          </Button>
          <Button
            variant="danger"
            icon={mode === 'pull' ? 'action.pull' : 'action.reject'}
            isDisabled={pending}
            onPress={send}
          >
            {mode === 'pull' ? 'Pull' : 'Reject'} {item.key}
          </Button>
        </div>
      </ModalDialog>
    </section>
  );
}
