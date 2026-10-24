import { useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { useQueries } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useListDecisions } from '../../api/generated/decisions/decisions';
import { getListFindingsQueryKey, listFindings } from '../../api/generated/findings/findings';

import {
  getGetItemHistoryQueryKey,
  getListCommentsQueryKey,
  getListItemAttachmentsQueryKey,
  useAddComment,
  useGetItemHistory,
  useListComments,
  useUploadItemAttachment,
} from '../../api/generated/items/items';
import type {
  AttachmentKind,
  AttachmentOut,
  DecisionOut,
  FindingOut,
  ItemDetailOut,
  TermsField,
  TermsRefOut,
} from '../../api/generated/model';
import { useListUsers } from '../../api/generated/users/users';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { SelectField, TextAreaField } from '../../ui/forms/fields';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import {
  ATTACHMENT_KIND_LABELS,
  CHANNEL_LABELS,
  MARKET_LABELS,
  PRODUCT_LABELS,
  RISK_TIER_LABELS,
  TERMS_FIELD_LABELS,
  formatBytes,
  formatDate,
} from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonText } from '../../ui/Skeleton';
import { DecisionRecord } from './DecisionRecord';
import { describeEvent } from './historyText';
import { PlacementsSection } from './Placements';

function PanelLoading({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="app-panel-skeleton">
      <SkeletonText width="70%" />
      <SkeletonText width="90%" />
      <SkeletonText width="50%" />
    </div>
  );
}

function PanelError({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <div className="app-inline-error" role="alert">
      <span>
        {what} didn’t load. {apiErrorMessage(error)}
      </span>
      <Button size="sm" onPress={onRetry}>
        Retry
      </Button>
    </div>
  );
}

// ---- Comments ------------------------------------------------------------------------------------

const commentDomId = (id: number) => `comment-${String(id)}`;

export function CommentsTab({
  itemId,
  versionN,
  canComment,
  highlightId,
  shownLinks,
}: {
  itemId: number;
  versionN: number;
  canComment: boolean;
  /** A linked comment (`?comment=`): scrolled into view, focused and briefly highlighted once it loads. */
  highlightId?: number;
  /**
   * Links already brought into view on this page. The tab panel remounts on every return to Comments while
   * `?comment=` stays in the URL; only the first showing takes focus and plays the highlight.
   */
  shownLinks?: Set<number>;
}) {
  const queryClient = useQueryClient();
  const comments = useListComments(itemId, { version_n: versionN });
  // Per link, not per mount: a second mention opened while Comments is showing must still be brought into view.
  // `shownLinks` is stable, so this recomputes only when the link changes (or the panel remounts).
  const fresh = useMemo(
    () => highlightId !== undefined && !(shownLinks?.has(highlightId) ?? false),
    [highlightId, shownLinks],
  );
  const loaded = comments.data?.some((c) => c.id === highlightId) === true;
  const done = useRef<number | null>(null);
  useEffect(() => {
    if (!fresh || !loaded || highlightId === undefined || done.current === highlightId) return;
    done.current = highlightId;
    shownLinks?.add(highlightId);
    const node = document.getElementById(commentDomId(highlightId));
    node?.scrollIntoView({ block: 'center' });
    node?.focus({ preventScroll: true });
  }, [fresh, loaded, highlightId, shownLinks]);
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const add = useAddComment({
    mutation: {
      onSuccess: () => {
        setBody('');
        void queryClient.invalidateQueries({ queryKey: getListCommentsQueryKey(itemId) });
        void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(itemId) });
      },
      onError: (e) => {
        setError(apiErrorMessage(e));
      },
    },
  });

  return (
    <div className="app-panel-stack">
      {comments.isPending ? (
        <PanelLoading label="Loading comments" />
      ) : comments.isError ? (
        <PanelError what="Comments" error={comments.error} onRetry={() => void comments.refetch()} />
      ) : comments.data.length === 0 ? (
        <EmptyState icon="action.comment" title={`No comments on v${String(versionN)}`} />
      ) : (
        <ol className="app-timeline">
          {comments.data.map((comment) => (
            <li
              key={comment.id}
              id={commentDomId(comment.id)}
              className="app-comment"
              {...(comment.id === highlightId
                ? { tabIndex: -1, 'aria-current': 'true' as const, 'data-linked': fresh ? 'true' : undefined }
                : {})}
            >
              <p className="app-timeline-meta">
                <span className="app-timeline-actor">{comment.author.name}</span>{' '}
                <RelativeAge at={comment.created_at} />
              </p>
              <p className="app-comment-body">{comment.body}</p>
            </li>
          ))}
        </ol>
      )}
      {canComment && (
        <form
          className="app-panel-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (body.trim() === '') {
              setError('Write a comment first.');
              return;
            }
            add.mutate({ itemId, data: { body: body.trim(), version_n: versionN } });
          }}
        >
          <TextAreaField
            label={`Comment on v${String(versionN)}`}
            value={body}
            onChange={(value) => {
              setBody(value);
              setError(null);
            }}
            errorMessage={error}
            rows={2}
          />
          <div>
            <Button type="submit" size="sm" icon="action.comment" isDisabled={add.isPending}>
              Comment
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

// ---- Details -------------------------------------------------------------------------------------

/**
 * "Personal loan offer terms v12" → one line per quoted field, in the Offer terms screen's words ("APR min:
 * 9.99%", "Loan terms (months): 24, 60"). A value quoted twice is listed once.
 */
export function groupTermsRefs(refs: readonly TermsRefOut[]): { label: string; quotes: string[] }[] {
  const groups = new Map<number, { label: string; fields: Map<TermsField, string[]> }>();
  for (const ref of refs) {
    const key = ref.offer_terms.id;
    const group = groups.get(key) ?? {
      label: `${PRODUCT_LABELS[ref.offer_terms.product]} offer terms v${String(ref.offer_terms.version)}`,
      fields: new Map<TermsField, string[]>(),
    };
    const values = group.fields.get(ref.field) ?? [];
    if (!values.includes(ref.quote)) values.push(ref.quote);
    group.fields.set(ref.field, values);
    groups.set(key, group);
  }
  return [...groups.values()].map(({ label, fields }) => ({
    label,
    quotes: [...fields].map(([field, values]) => `${TERMS_FIELD_LABELS[field]}: ${values.join(', ')}`),
  }));
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="app-detail-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function DetailsTab({
  item,
  onShowLiveDiff,
}: {
  item: ItemDetailOut;
  /** A drift re-review: the placement's "Live page vs approved vN" opens in the center pane. */
  onShowLiveDiff?: (placementId: number) => void;
}) {
  const terms = groupTermsRefs(item.current_version?.terms_refs ?? []);
  const run =
    item.planned_first_run === null
      ? '—'
      : `${formatDate(item.planned_first_run)} – ${item.planned_last_run === null ? 'open-ended' : formatDate(item.planned_last_run)}`;
  return (
    <div className="app-panel-stack">
      <dl className="app-details">
        <Row label="Product">{PRODUCT_LABELS[item.product]}</Row>
        <Row label="Channel">{CHANNEL_LABELS[item.channel]}</Row>
        <Row label="Partner">
          {item.partner === null ? (
            'None (first-party)'
          ) : (
            // The partner's page holds the agreement reviewers check affiliate copy against.
            <Link
              to="/partners/$partnerId"
              params={{ partnerId: String(item.partner.id) }}
              className="app-link"
            >
              {item.partner.name}
            </Link>
          )}
        </Row>
        <Row label="Markets">{item.markets.map((m) => MARKET_LABELS[m]).join(', ')}</Row>
        <Row label="Planned run">{run}</Row>
        <Row label="Prescreened offer">{item.is_prescreen ? 'Yes' : 'No'}</Row>
        <Row label="Risk tier">
          {RISK_TIER_LABELS[item.risk_tier]}
          {item.risk_tier_overridden ? ' (overridden)' : ' (derived at intake)'}
        </Row>
        <Row label="Submitted by">{item.owner?.name ?? item.legacy_submitter}</Row>
        <Row label="Assignee">{item.assignee?.name ?? 'Unassigned'}</Row>
        <Row label="Submitted">
          {formatDate(item.submitted_at)} · <RelativeAge at={item.submitted_at} />
        </Row>
        {item.approval_expires_at !== null && (
          <Row label="Approval expires">{formatDate(item.approval_expires_at)}</Row>
        )}
        {item.retention_until !== null && <Row label="Retain until">{formatDate(item.retention_until)}</Row>}
        {item.source_url !== null && item.source_url !== '' && (
          <Row label="Fetched from">{item.source_url}</Row>
        )}
        {item.tags.length > 0 && <Row label="Tags">{item.tags.join(', ')}</Row>}
        {item.notes !== '' && <Row label="Notes">{item.notes}</Row>}
        {item.is_legacy && <Row label="Legacy ref">{item.legacy_ref ?? '—'}</Row>}
      </dl>
      {item.latest_decision !== null && (
        <section aria-labelledby="decision-record-title">
          <h3 id="decision-record-title" className="app-panel-heading">
            Decision record
          </h3>
          <DecisionRecord decision={item.latest_decision} />
        </section>
      )}
      {/* Placements exist only once an approval has been recorded. */}
      {item.approved_at !== null && (
        <PlacementsSection
          itemId={item.id}
          ownerId={item.owner?.id ?? null}
          onShowLiveDiff={onShowLiveDiff}
        />
      )}
      <section aria-labelledby="terms-title">
        <h3 id="terms-title" className="app-panel-heading">
          Offer terms quoted
        </h3>
        {terms.length === 0 ? (
          <p className="app-muted">No rate, fee, or example claims linked to offer terms.</p>
        ) : (
          terms.map((group) => (
            <div key={group.label} className="app-terms-group">
              <p className="app-terms-label">{group.label}</p>
              <ul className="app-plain-list">
                {group.quotes.map((q) => (
                  <li key={q} className="app-figure">
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
    </div>
  );
}

// ---- Evidence ------------------------------------------------------------------------------------

const UPLOAD_KINDS = (Object.keys(ATTACHMENT_KIND_LABELS) as AttachmentKind[]).filter(
  (k) => k !== 'agreement',
);

export function EvidenceTab({
  itemId,
  attachments,
  loading,
  canUpload,
}: {
  itemId: number;
  attachments: readonly AttachmentOut[];
  loading: boolean;
  canUpload: boolean;
}) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<AttachmentKind | null>('substantiation');
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadItemAttachment({
    mutation: {
      onSuccess: () => {
        setError(null);
        if (fileInput.current !== null) fileInput.current.value = '';
        void queryClient.invalidateQueries({ queryKey: getListItemAttachmentsQueryKey(itemId) });
        void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(itemId) });
      },
      onError: (e) => {
        setError(apiErrorMessage(e));
      },
    },
  });

  return (
    <div className="app-panel-stack">
      {loading ? (
        <PanelLoading label="Loading evidence" />
      ) : attachments.length === 0 ? (
        <EmptyState icon="entity.item" title="No evidence attached">
          Rate sheets, substantiation, prescreen criteria, and screenshots go here.
        </EmptyState>
      ) : (
        <ul className="app-evidence-list">
          {attachments.map((a) => (
            <li key={a.id} className="app-evidence">
              <a href={a.download_url} className="app-link">
                {a.original_name}
              </a>
              <p className="app-timeline-meta">
                {ATTACHMENT_KIND_LABELS[a.kind]} · {formatBytes(a.size_bytes)} · {a.uploaded_by.name}{' '}
                <RelativeAge at={a.uploaded_at} />
              </p>
              <p className="app-hash" title={a.sha256}>
                sha256 {a.sha256.slice(0, 12)}…
              </p>
            </li>
          ))}
        </ul>
      )}
      {canUpload && (
        <form
          className="app-panel-form"
          onSubmit={(event) => {
            event.preventDefault();
            const file = fileInput.current?.files?.[0];
            if (file === undefined || kind === null) {
              setError('Choose a file and its kind.');
              return;
            }
            upload.mutate({ itemId, data: { kind, file } });
          }}
        >
          <SelectField
            label="Kind"
            value={kind}
            onChange={setKind}
            options={UPLOAD_KINDS.map((k) => ({ id: k, label: ATTACHMENT_KIND_LABELS[k] }))}
          />
          <label className="app-field">
            <span className="app-field-label">File</span>
            <input ref={fileInput} type="file" className="app-file-input" />
          </label>
          {error !== null && (
            <p className="app-field-error" role="alert">
              {error}
            </p>
          )}
          <div>
            <Button type="submit" size="sm" isDisabled={upload.isPending}>
              {upload.isPending ? 'Uploading…' : 'Add evidence'}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

// ---- History -------------------------------------------------------------------------------------

/**
 * Finding events carry the finding's id and rule id; the sentence uses the finding's message instead (spec §5.4).
 * Findings are listed per version, so this reads every version the history's finding events point at.
 */
function useFindingMessages(itemId: number, versionNs: readonly number[]): ReadonlyMap<number, string> {
  return useQueries({
    queries: versionNs.map((n) => ({
      queryKey: getListFindingsQueryKey(itemId, { version_n: n }),
      queryFn: ({ signal }: { signal: AbortSignal }) => listFindings(itemId, { version_n: n }, { signal }),
    })),
    combine: findingMessages,
  });
}

/** Stable, so useQueries only recombines when a result changes. */
function findingMessages(results: readonly { data?: readonly FindingOut[] }[]): ReadonlyMap<number, string> {
  return new Map(results.flatMap((r) => (r.data ?? []).map((f) => [f.id, f.message] as const)));
}

const FINDING_EVENTS = new Set(['finding.accepted', 'finding.dismissed', 'finding.reopened']);

export function HistoryTab({ item }: { item: ItemDetailOut }) {
  const history = useGetItemHistory(item.id);
  const users = useListUsers();
  const decisions = useListDecisions(item.id);
  const versionIds = useMemo(() => new Map(item.versions.map((v) => [v.id, v.n])), [item.versions]);
  const findingVersions = useMemo(() => {
    const ns = new Set<number>();
    for (const entry of history.data?.entries ?? []) {
      if (FINDING_EVENTS.has(entry.type) && 'version_id' in entry.payload) {
        const n = versionIds.get(entry.payload.version_id);
        if (n !== undefined) ns.add(n);
      }
    }
    return [...ns].sort((a, b) => a - b);
  }, [history.data, versionIds]);
  const findings = useFindingMessages(item.id, findingVersions);
  const records = useMemo(
    () => new Map<number, DecisionOut>((decisions.data ?? []).map((d) => [d.id, d])),
    [decisions.data],
  );
  const lookups = useMemo(
    () => ({
      versions: versionIds,
      users: new Map((users.data ?? []).map((u) => [u.id, u.display_name || u.email])),
      findings,
    }),
    [versionIds, users.data, findings],
  );

  if (history.isPending) {
    return <PanelLoading label="Loading history" />;
  }
  if (history.isError) {
    return <PanelError what="History" error={history.error} onRetry={() => void history.refetch()} />;
  }
  const entries = [...history.data.entries].sort((a, b) => b.at.localeCompare(a.at) || b.id - a.id);
  return (
    <ol className="app-timeline" aria-label="Event history, newest first">
      {entries.map((entry) => {
        const record =
          entry.type === 'decision.recorded' ? records.get(entry.payload.decision_id) : undefined;
        return (
          <li key={entry.id} className="app-timeline-entry">
            <p className="app-timeline-text">{describeEvent(entry, lookups)}</p>
            <p className="app-timeline-meta">
              <span className="app-timeline-actor">{entry.actor?.name ?? 'System'}</span>{' '}
              <RelativeAge at={entry.at} />
            </p>
            {record !== undefined && (
              <details className="app-record-toggle">
                <summary>
                  <Icon name="action.expand" size={12} className="app-record-caret" />
                  Decision record
                </summary>
                <DecisionRecord decision={record} />
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}
