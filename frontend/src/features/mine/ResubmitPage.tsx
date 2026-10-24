/*
 * Resubmit (product-spec status machine): after changes were requested the marketer submits v+1 with a
 * note; after a pull (withdrawn) or an expired approval they start a new round. The editor opens on the
 * current version with live checks, and "Changes vs v{n}" shows the word diff before anything is sent.
 */
import { revalidateLogic, useForm, useSelector } from '@tanstack/react-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { useState } from 'react';
import { ToggleButton, ToggleButtonGroup } from 'react-aria-components';
import { z } from 'zod';

import { useListFindings } from '../../api/generated/findings/findings';
import {
  getGetItemQueryKey,
  getListItemsQueryKey,
  resubmitItem,
  startNewRound,
  useGetItem,
  useListItemAttachments,
} from '../../api/generated/items/items';
import { ResubmitItemBody } from '../../api/generated/items/items.zod';
import type { CheckPreviewIn, ItemDetailOut } from '../../api/generated/model';
import { ApiError } from '../../api/mutator';
import { Button } from '../../ui/Button';
import { CopyEditor } from '../../ui/copy/CopyEditor';
import { DiffText, countChanges } from '../../ui/copy/DiffText';
import { useLiveChecks } from '../../ui/copy/useLiveChecks';
import { wordDiff } from '../../ui/copy/wordDiff';
import { EmptyState } from '../../ui/EmptyState';
import { FindingSummary } from '../../ui/findings/FindingSummary';
import { LiveFindings } from '../../ui/findings/LiveFindings';
import { apiErrorMessage, fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { TextAreaField } from '../../ui/forms/fields';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { ItemKey } from '../../ui/ItemKey';
import { formatDate, plural } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonText } from '../../ui/Skeleton';
import { showToast } from '../../ui/toast';

type Mode = 'resubmit' | 'new_round';

const FIELD_NAMES = ['content_text', 'note'] as const;

const schema = z.object({
  content_text: z
    .string()
    .refine((text) => text.trim() !== '', "The copy can't be empty.")
    .refine(
      (text) => text.length <= (ResubmitItemBody.shape.content_text.maxLength ?? Infinity),
      'The copy is too long.',
    ),
  note: z.string().max(ResubmitItemBody.shape.note.unwrap().maxLength ?? Infinity, 'Shorten the note.'),
});

function modeFor(status: ItemDetailOut['status']): Mode | null {
  if (status === 'changes_requested') return 'resubmit';
  if (status === 'withdrawn' || status === 'expired') return 'new_round';
  return null;
}

/** Why there's no form, in one line (spec §5.4). */
function notResubmittable(item: ItemDetailOut): string {
  switch (item.status) {
    case 'draft':
      return `${item.key} hasn't been submitted yet.`;
    case 'submitted':
    case 'in_review':
      return `${item.key} is in review. You can resubmit after a reviewer requests changes.`;
    case 'needs_rereview':
      return `${item.key} is back in review. Compliance decides what happens next.`;
    case 'approved':
      return `${item.key} is approved. Nothing to resubmit.`;
    case 'rejected':
      return `${item.key} was rejected. Submit the content again as a new item.`;
    default:
      return `${item.key} can't be resubmitted.`;
  }
}

function RequestedChanges({ item }: { item: ItemDetailOut }) {
  const decision = item.latest_decision;
  const versionN = decision?.version_n ?? item.current_version_n ?? undefined;
  const findings = useListFindings(item.id, { version_n: versionN });
  const accepted = (findings.data ?? []).filter((finding) => finding.state === 'accepted');

  return (
    <section aria-labelledby="requested-title" className="app-requested">
      <h2 id="requested-title" className="app-requested-title">
        Requested changes
      </h2>
      {decision?.outcome === 'changes_requested' && (
        <div className="app-requested-decision">
          <p className="app-requested-by">
            {decision.approver.name} on v{decision.version_n} · <RelativeAge at={decision.decided_at} />
          </p>
          <p className="app-requested-reason">{decision.reason}</p>
        </div>
      )}
      {decision?.outcome !== 'changes_requested' && accepted.length === 0 && findings.isSuccess && (
        <p className="app-muted">No reason recorded. The item&apos;s comments may say more.</p>
      )}
      {accepted.length > 0 && (
        <ul className="app-requested-list" aria-label="Accepted findings">
          {accepted.map((finding) => (
            <li key={finding.id}>
              <FindingSummary
                severity={finding.severity}
                source={finding.source}
                message={finding.message}
                citation={finding.citation}
                quote={finding.quote}
                suggestedFix={finding.suggested_fix}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RoundContext({ item }: { item: ItemDetailOut }) {
  const text =
    item.status === 'withdrawn'
      ? `Pulled from where it ran. Fix the copy and start round ${String(item.round + 1)}.`
      : `Approval expired${
          item.approval_expires_at === null ? '' : ` ${formatDate(item.approval_expires_at)}`
        }. Start round ${String(item.round + 1)} to have it reviewed again.`;
  return <p className="app-resubmit-context">{text}</p>;
}

function ResubmitForm({
  item,
  mode,
  context,
}: {
  item: ItemDetailOut;
  mode: Mode;
  context: React.ReactNode;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const attachments = useListItemAttachments(item.id);
  const [view, setView] = useState<'edit' | 'diff'>('edit');
  const [formError, setFormError] = useState<string | null>(null);
  const original = item.current_version?.content_text ?? '';
  const currentN = item.current_version_n ?? 1;

  const send = useMutation({
    mutationFn: ({ content_text, note }: { content_text: string; note: string }) =>
      mode === 'resubmit'
        ? resubmitItem(item.id, { content_text, note })
        : startNewRound(item.id, { content_text }),
    onSuccess: (version) => {
      showToast({
        title: mode === 'resubmit' ? 'Resubmitted' : 'New round started',
        description: (
          <>
            <ItemKey value={item.key} copyable={false} /> v{version.n}
          </>
        ),
      });
      void queryClient.invalidateQueries({ queryKey: getGetItemQueryKey(item.id) });
      void queryClient.invalidateQueries({ queryKey: getListItemsQueryKey() });
      void navigate({ to: '/items/$itemId', params: { itemId: String(item.id) } });
    },
    onError: (error) => {
      const { fields, form: line } = fieldErrorsFrom(error, FIELD_NAMES);
      for (const name of FIELD_NAMES) {
        form.setFieldMeta(name, (prev) => ({
          ...prev,
          errorMap: { ...prev.errorMap, onServer: fields[name] },
        }));
      }
      setFormError(line);
    },
  });

  const form = useForm({
    defaultValues: { content_text: original, note: '' },
    validationLogic: revalidateLogic(),
    validators: { onDynamic: schema },
    listeners: {
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
    onSubmit: ({ value }) => {
      setFormError(null);
      send.mutate(value);
    },
  });

  const draft = useSelector(form.store, (state) => state.values.content_text);
  const unchanged = draft === original;
  // An expired approval can run again as-is; a change request or a pull needs an edit.
  const needsEdit = item.status !== 'expired';
  const diff = wordDiff(original, draft);
  const changes = countChanges(diff);

  const preview: CheckPreviewIn = {
    content_text: draft,
    product: item.product,
    channel: item.channel,
    markets: item.markets,
    partner_id: item.partner?.id ?? null,
    is_prescreen: item.is_prescreen,
    attachment_kinds: [...new Set((attachments.data ?? []).map((attachment) => attachment.kind))],
  };
  const checks = useLiveChecks(item.markets.length === 0 ? null : preview);
  const submitLabel = mode === 'resubmit' ? 'Resubmit' : 'Start new round';

  return (
    <form
      className="app-resubmit-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void form.handleSubmit();
      }}
    >
      <div className="app-resubmit-main">
        {context}
        <div className="app-resubmit-toolbar">
          <ToggleButtonGroup
            aria-label="View"
            selectionMode="single"
            disallowEmptySelection
            selectedKeys={[view]}
            onSelectionChange={(keys) => {
              const [next] = [...keys];
              if (next === 'edit' || next === 'diff') setView(next);
            }}
            className="app-segmented"
          >
            <ToggleButton id="edit" className="app-segment">
              Edit
            </ToggleButton>
            <ToggleButton id="diff" className="app-segment">
              Changes vs v{currentN}
            </ToggleButton>
          </ToggleButtonGroup>
          <span className="app-resubmit-summary" role="status">
            {unchanged ? '' : plural(changes, 'change')}
          </span>
        </div>

        {view === 'edit' ? (
          <form.Field name="content_text">
            {(field) => (
              <CopyEditor
                label="Copy"
                hideLabel
                name="content_text"
                value={field.state.value}
                onChange={field.handleChange}
                marks={checks.marks}
                errorMessage={fieldErrorText(field.state.meta.errors)}
              />
            )}
          </form.Field>
        ) : (
          <div className="app-resubmit-diff" aria-label={`Changes vs v${String(currentN)}`} role="region">
            <DiffText segments={diff} />
          </div>
        )}

        {mode === 'resubmit' && (
          <form.Field name="note">
            {(field) => (
              <TextAreaField
                label="What changed"
                description="For the reviewer. Optional."
                rows={2}
                value={field.state.value}
                onChange={field.handleChange}
                onBlur={field.handleBlur}
                errorMessage={fieldErrorText(field.state.meta.errors)}
              />
            )}
          </form.Field>
        )}

        <div className="app-submit-actions app-resubmit-actions">
          {formError !== null && (
            <p className="app-form-error" role="alert">
              {formError}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            isDisabled={needsEdit && unchanged}
            isPending={send.isPending}
            aria-describedby={needsEdit && unchanged ? 'resubmit-blocked' : undefined}
          >
            {submitLabel}
          </Button>
          {needsEdit && unchanged && (
            <span id="resubmit-blocked" className="app-muted">
              No changes yet
            </span>
          )}
        </div>
      </div>

      <aside className="app-resubmit-live">
        <LiveFindings checks={checks} className="app-live" />
      </aside>
    </form>
  );
}

export function ResubmitPage({ itemId }: { itemId: number }) {
  const item = useGetItem(itemId);
  const key = item.data?.key ?? `CP-${String(itemId)}`;

  if (item.isPending) {
    return (
      <div className="app-resubmit" aria-busy="true">
        <h1 className="app-page-title">
          <SkeletonText width="14rem" />
        </h1>
        <div role="status" aria-label="Loading the item" className="app-resubmit-loading">
          <SkeletonText width="60%" />
          <SkeletonText width="80%" />
          <SkeletonText width="45%" />
        </div>
      </div>
    );
  }

  if (item.isError) {
    // The generated hook types errors as the body; at runtime the mutator throws ApiError.
    const error: unknown = item.error;
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="app-resubmit">
        <h1 className="app-page-title">Resubmit {key}</h1>
        {notFound ? (
          <EmptyState icon="entity.item" title={`${key} not found`}>
            It may have been deleted, or the link is wrong.
          </EmptyState>
        ) : (
          <div className="app-mine-error" role="alert">
            <p className="app-mine-error-title">Couldn&apos;t load {key}.</p>
            <p className="app-muted">{apiErrorMessage(item.error)}</p>
            <Button
              size="sm"
              onPress={() => {
                void item.refetch();
              }}
            >
              Retry
            </Button>
          </div>
        )}
      </div>
    );
  }

  const data = item.data;
  const mode = modeFor(data.status);

  return (
    <div className="app-resubmit">
      <header className="app-resubmit-header">
        <h1 className="app-page-title">
          {mode === 'new_round' ? 'New round' : 'Resubmit'} <span className="font-mono">{data.key}</span>
        </h1>
        <p className="app-resubmit-subtitle">
          <Link to="/items/$itemId" params={{ itemId: String(data.id) }} className="app-mine-link">
            {data.title}
          </Link>
          <span className="app-muted">
            {' '}
            · Round {data.round} · v{data.current_version_n ?? 1}
          </span>
        </p>
      </header>
      {mode === null ? (
        <p className="app-resubmit-context">{notResubmittable(data)}</p>
      ) : (
        <ResubmitForm
          item={data}
          mode={mode}
          context={mode === 'resubmit' ? <RequestedChanges item={data} /> : <RoundContext item={data} />}
        />
      )}
    </div>
  );
}
