/*
 * The human gate on send_email (decisions.md "Assistant"): the draft as the model wrote it, and Approve /
 * Edit / Reject. Recipients are shown exactly as given; the server checks them against the directory and
 * answers an edit with a 422 on the field, which lands under that field here (spec §6.1).
 */
import { revalidateLogic, useForm } from '@tanstack/react-form';
import { useMutation } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';

import { Button } from '../../ui/Button';
import { apiErrorBody, fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { TextAreaField, TextInput } from '../../ui/forms/fields';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { Icon } from '../../ui/Icon';
import type { ApprovalResponse, ToolApproval } from './types';

const FIELD_NAMES = ['to', 'subject', 'body'] as const;

/** "a@x, b@x" or one per line -> ["a@x", "b@x"]. */
export function parseRecipients(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((part) => part.trim())
    .filter((part) => part !== '');
}

const editSchema = z.object({
  to: z.string().refine((value) => parseRecipients(value).length > 0, 'Add at least one recipient.'),
  subject: z.string().trim().min(1, 'Add a subject.').max(300, 'Keep the subject under 300 characters.'),
  body: z.string().trim().min(1, 'Add a message.'),
});

function itemIdOf(key: string | null | undefined): string | undefined {
  const match = /^CP-(\d+)$/.exec(key ?? '');
  return match?.[1];
}

function ItemRow({ itemKey }: { itemKey: string | null | undefined }) {
  const itemId = itemIdOf(itemKey);
  if (itemId === undefined) return null;
  return (
    <div className="app-assistant-draft-row">
      <dt>Item</dt>
      <dd>
        <Link to="/items/$itemId" params={{ itemId }} className="app-assistant-item-link">
          {itemKey}
        </Link>
      </dd>
    </div>
  );
}

function Draft({ approval }: { approval: ToolApproval }) {
  const { to, subject, body, item_key: itemKey } = approval.args;
  return (
    <dl className="app-assistant-draft">
      <div className="app-assistant-draft-row">
        <dt>To</dt>
        <dd>
          <ul className="app-assistant-recipients" aria-label="Recipients">
            {to.map((address) => (
              <li key={address} className="app-assistant-recipient">
                {address}
              </li>
            ))}
          </ul>
        </dd>
      </div>
      <div className="app-assistant-draft-row">
        <dt>Subject</dt>
        <dd>{subject}</dd>
      </div>
      <ItemRow itemKey={itemKey} />
      <div className="app-assistant-draft-body">
        <dt className="sr-only">Body</dt>
        <dd>{body}</dd>
      </div>
    </dl>
  );
}

function EditForm({
  approval,
  pending,
  onSend,
  onCancel,
}: {
  approval: ToolApproval;
  pending: boolean;
  onSend: (response: ApprovalResponse, onError: (error: unknown) => void) => void;
  onCancel: () => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm({
    defaultValues: {
      to: approval.args.to.join(', '),
      subject: approval.args.subject,
      body: approval.args.body,
    },
    validationLogic: revalidateLogic(),
    validators: { onDynamic: editSchema },
    listeners: {
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
    onSubmit: ({ value }) => {
      setFormError(null);
      onSend(
        {
          type: 'edit',
          edited_action: {
            name: 'send_email',
            args: {
              to: parseRecipients(value.to),
              subject: value.subject.trim(),
              body: value.body,
              item_key: approval.args.item_key ?? null,
            },
          },
        },
        (error) => {
          const { fields, form: line } = fieldErrorsFrom(error, FIELD_NAMES);
          for (const name of FIELD_NAMES) {
            form.setFieldMeta(name, (prev) => ({
              ...prev,
              errorMap: { ...prev.errorMap, onServer: fields[name] },
            }));
          }
          setFormError(line);
        },
      );
    },
  });

  return (
    <form
      className="app-assistant-edit"
      noValidate
      aria-label="Edit email"
      onSubmit={(event) => {
        event.preventDefault();
        void form.handleSubmit();
      }}
    >
      {itemIdOf(approval.args.item_key) !== undefined && (
        <dl className="app-assistant-draft">
          <ItemRow itemKey={approval.args.item_key} />
        </dl>
      )}
      <form.Field name="to">
        {(field) => (
          <TextAreaField
            label="To"
            description="Comma-separated or one per line"
            rows={2}
            // Edit was just pressed and unmounted itself: focus follows to the first field.
            autoFocus
            name={field.name}
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
            isDisabled={pending}
          />
        )}
      </form.Field>
      <form.Field name="subject">
        {(field) => (
          <TextInput
            label="Subject"
            name={field.name}
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
            isDisabled={pending}
          />
        )}
      </form.Field>
      <form.Field name="body">
        {(field) => (
          <TextAreaField
            label="Body"
            rows={6}
            name={field.name}
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
            isDisabled={pending}
          />
        )}
      </form.Field>
      {formError !== null && (
        <p className="app-form-error" role="alert">
          {formError}
        </p>
      )}
      <div className="app-assistant-approval-actions">
        <Button type="submit" variant="primary" size="sm" icon="action.send" isDisabled={pending}>
          Send edited
        </Button>
        <Button size="sm" variant="ghost" onPress={onCancel} isDisabled={pending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function ApprovalCard({
  approval,
  onRespond,
  focusOnMount = false,
}: {
  approval: ToolApproval;
  onRespond: (response: ApprovalResponse) => Promise<void>;
  /** The draft arrived while you were in the panel: take focus so the next Tab is Send email. */
  focusOnMount?: boolean;
}) {
  const [mode, setMode] = useState<'review' | 'edit' | 'reject'>('review');
  const [reason, setReason] = useState('');
  const respond = useMutation({ mutationFn: onRespond });
  const pending = respond.isPending;
  const heading = useRef<HTMLHeadingElement>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const declineButton = useRef<HTMLButtonElement>(null);
  // Which button gets focus back when an edit or a decline is cancelled.
  const returnTo = useRef<'edit' | 'reject' | null>(null);

  useEffect(() => {
    if (!focusOnMount) return;
    // Only from inside the panel (the composer just locked) or nowhere; never out of the page.
    const active = document.activeElement;
    const panel = heading.current?.closest('aside');
    if (active === null || active === document.body || (panel?.contains(active) ?? false)) {
      heading.current?.focus();
    }
  }, [focusOnMount]);
  useEffect(() => {
    if (mode !== 'review' || returnTo.current === null) return;
    (returnTo.current === 'edit' ? editButton : declineButton).current?.focus();
    returnTo.current = null;
  }, [mode]);

  const cancel = () => {
    if (mode === 'review' || pending) return;
    respond.reset();
    returnTo.current = mode;
    setMode('review');
  };
  // Edit and decline failures are shown on the card unless the edit form owns them (field errors).
  const cardError =
    mode !== 'edit' && respond.isError
      ? (apiErrorBody(respond.error)?.message ?? "Couldn't send your answer. Try again.")
      : null;

  return (
    <section
      className="app-assistant-approval"
      aria-labelledby="assistant-approval-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && mode !== 'review') {
          event.preventDefault();
          cancel();
        }
      }}
    >
      <header className="app-assistant-approval-head">
        <Icon name="feedback.awaiting" />
        <h3
          id="assistant-approval-title"
          ref={heading}
          tabIndex={-1}
          className="app-assistant-approval-title"
        >
          Email draft — needs your approval
        </h3>
      </header>
      <p className="app-assistant-approval-note">Nothing is sent until you approve.</p>

      {mode === 'edit' ? (
        <EditForm
          approval={approval}
          pending={pending}
          onSend={(response, onError) => {
            respond.mutate(response, { onError });
          }}
          onCancel={cancel}
        />
      ) : (
        <Draft approval={approval} />
      )}

      {mode === 'reject' && (
        <TextAreaField
          label="Reason (optional)"
          description="Tells the assistant what to change."
          rows={2}
          value={reason}
          onChange={setReason}
          isDisabled={pending}
          autoFocus
        />
      )}

      {cardError !== null && (
        <p className="app-form-error" role="alert">
          {cardError}
        </p>
      )}

      {mode === 'review' && (
        <div className="app-assistant-approval-actions">
          <Button
            variant="primary"
            size="sm"
            icon="action.send"
            isDisabled={pending}
            onPress={() => {
              respond.mutate({ type: 'approve' });
            }}
          >
            Send email
          </Button>
          <Button
            ref={editButton}
            size="sm"
            icon="action.edit"
            isDisabled={pending}
            onPress={() => {
              respond.reset();
              setMode('edit');
            }}
          >
            Edit
          </Button>
          <Button
            ref={declineButton}
            size="sm"
            icon="action.close"
            isDisabled={pending}
            onPress={() => {
              respond.reset();
              setMode('reject');
            }}
          >
            Don&apos;t send
          </Button>
        </div>
      )}
      {mode === 'reject' && (
        <div className="app-assistant-approval-actions">
          <Button
            size="sm"
            icon="action.close"
            isDisabled={pending}
            onPress={() => {
              const message = reason.trim();
              respond.mutate(message === '' ? { type: 'reject' } : { type: 'reject', message });
            }}
          >
            Don&apos;t send
          </Button>
          <Button size="sm" variant="ghost" isDisabled={pending} onPress={cancel}>
            Cancel
          </Button>
        </div>
      )}
    </section>
  );
}
