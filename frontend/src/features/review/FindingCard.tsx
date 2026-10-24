import { useState } from 'react';

import type { FindingOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { FindingSummary } from '../../ui/findings/FindingSummary';
import { TextAreaField } from '../../ui/forms/fields';
import { Kbd } from '../../ui/Kbd';
import { RelativeAge } from '../../ui/RelativeAge';

export const findingCardId = (id: number | string) => `finding-${String(id)}`;
export const findingMessageId = (id: number | string) => `finding-msg-${String(id)}`;

export interface FindingCardProps {
  finding: FindingOut;
  active: boolean;
  canTriage: boolean;
  dismissing: boolean;
  pending: boolean;
  onActivate: () => void;
  onAccept: () => void;
  onStartDismiss: () => void;
  onCancelDismiss: () => void;
  onDismiss: (reason: string) => void;
  onReopen: () => void;
}

function StateLine({ finding }: { finding: FindingOut }) {
  if (finding.state === 'open') {
    return null;
  }
  const who = finding.resolved_by?.name ?? 'Someone';
  const when = finding.resolved_at === null ? null : <RelativeAge at={finding.resolved_at} />;
  if (finding.state === 'accepted') {
    return (
      <div className="app-finding-state" data-state="accepted">
        <p>
          Accepted by {who} · {when}
        </p>
      </div>
    );
  }
  return (
    <div className="app-finding-state" data-state="dismissed">
      <p>
        {finding.carried_from_id === null ? (
          <>
            Dismissed by {who} · {when}
          </>
        ) : (
          'Dismissal carried from an earlier version (same rule, same text)'
        )}
      </p>
      {finding.reason !== '' && <p className="app-finding-reason">{finding.reason}</p>}
    </div>
  );
}

function DismissForm({
  onDismiss,
  onCancel,
  pending,
}: {
  onDismiss: (reason: string) => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    if (reason.trim() === '') {
      setError('Say why this finding doesn’t apply.');
      return;
    }
    onDismiss(reason.trim());
  };
  return (
    <form
      className="app-dismiss-form"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <TextAreaField
        label="Reason for dismissing"
        value={reason}
        onChange={(value) => {
          setReason(value);
          setError(null);
        }}
        errorMessage={error}
        rows={2}
        autoFocus
        description="Enter to dismiss · Shift+Enter for a new line"
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
          } else if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <div className="app-finding-actions">
        <Button type="submit" size="sm" isDisabled={pending}>
          Dismiss
        </Button>
        <Button size="sm" variant="ghost" onPress={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** One finding: what it says, its triage state, and accept / dismiss / reopen. */
export function FindingCard({
  finding,
  active,
  canTriage,
  dismissing,
  pending,
  onActivate,
  onAccept,
  onStartDismiss,
  onCancelDismiss,
  onDismiss,
  onReopen,
}: FindingCardProps) {
  return (
    // The card is a focus target for n/p (tabIndex -1) and a click target that selects its span; its
    // buttons are the keyboard path for actions, so the container itself needs no key handler.
    <article
      id={findingCardId(finding.id)}
      className="app-finding-card"
      data-active={active ? 'true' : undefined}
      data-state={finding.state}
      aria-current={active ? 'true' : undefined}
      aria-label={`${finding.message}, ${finding.state}`}
      tabIndex={-1}
      onClick={onActivate}
    >
      <FindingSummary
        id={findingMessageId(finding.id)}
        severity={finding.severity}
        source={finding.source}
        message={finding.message}
        citation={finding.citation}
        quote={finding.quote}
        // Accepted = must change: the fix is still the point. Dismissed: no longer relevant.
        suggestedFix={finding.state === 'dismissed' ? undefined : finding.suggested_fix}
        quiet={finding.state !== 'open'}
      />
      <StateLine finding={finding} />
      {canTriage && finding.state === 'open' && !dismissing && (
        <div className="app-finding-actions">
          <Button size="sm" isDisabled={pending} onPress={onAccept}>
            Accept
          </Button>
          <Button size="sm" variant="ghost" isDisabled={pending} onPress={onStartDismiss}>
            Dismiss…
          </Button>
          {active && (
            <span className="app-finding-keys" aria-hidden="true">
              <Kbd keys={['A']} /> <Kbd keys={['D']} />
            </span>
          )}
        </div>
      )}
      {canTriage && dismissing && (
        <DismissForm onDismiss={onDismiss} onCancel={onCancelDismiss} pending={pending} />
      )}
      {canTriage && finding.state !== 'open' && (
        <div className="app-finding-actions">
          <Button size="sm" variant="ghost" isDisabled={pending} onPress={onReopen}>
            Reopen
          </Button>
        </div>
      )}
    </article>
  );
}
