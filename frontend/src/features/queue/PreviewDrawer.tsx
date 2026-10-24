/*
 * Preview drawer (spec §5.3: triage without a full page load). Non-modal, so j/k keep moving through the queue
 * and the drawer follows. Summary, open findings by severity, the latest decision, notes and tags (editable
 * for the submitter or a reviewer), and the way into the full review.
 */
import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';
import { Label, TextArea, TextField } from 'react-aria-components';

import { useListFindings } from '../../api/generated/findings/findings';
import { useGetItem } from '../../api/generated/items/items';
import type { DecisionOut, FindingOut, ItemDetailOut } from '../../api/generated/model';
import { RiskTierBadge, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { errorMessage, errorStatus } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { ItemKey } from '../../ui/ItemKey';
import { Kbd } from '../../ui/Kbd';
import type { Viewer } from '../../ui/layout/Viewer';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonText } from '../../ui/Skeleton';
import { CHANNEL_LABEL, OUTCOME_LABEL, PRODUCT_LABEL, REOPEN_REASON_LABEL, roundLabel } from './labels';
import { reviewPath } from './reviewPath';
import { TagEditor } from './TagEditor';
import { canEditFields, canEditRisk, useItemPatch } from './useItemPatch';

export const PREVIEW_HEADING_ID = 'queue-preview-title';

const dateFormat = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' });

function formatDate(value: string | null): string {
  if (value === null) return '—';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? '—' : dateFormat.format(date);
}

function runDates(item: ItemDetailOut): string {
  if (item.planned_first_run === null) return '—';
  const first = formatDate(item.planned_first_run);
  return item.planned_last_run === null ? `From ${first}` : `${first} – ${formatDate(item.planned_last_run)}`;
}

function FindingsSummary({ itemId, fallback }: { itemId: number; fallback: number }) {
  const findings = useListFindings(itemId);
  if (findings.isPending) return <SkeletonText width="9rem" />;
  if (findings.isError) {
    return <span>{fallback === 1 ? '1 open finding' : `${String(fallback)} open findings`}</span>;
  }
  const open = findings.data.filter((f: FindingOut) => f.state === 'open');
  const blocking = open.filter((f) => f.severity === 'blocking').length;
  const warning = open.length - blocking;
  if (open.length === 0) {
    return <span className="text-muted">No open findings</span>;
  }
  return (
    <span className="app-drawer-findings">
      {blocking > 0 && (
        <span className="app-drawer-severity" data-tone="error">
          <Icon name="severity.blocking" size={14} />
          {`${String(blocking)} blocking`}
        </span>
      )}
      {warning > 0 && (
        <span className="app-drawer-severity" data-tone="warning">
          <Icon name="severity.warning" size={14} />
          {`${String(warning)} ${warning === 1 ? 'warning' : 'warnings'}`}
        </span>
      )}
    </span>
  );
}

function LatestDecision({ decision }: { decision: DecisionOut | null }) {
  if (decision === null) return <p className="text-muted">No decision yet</p>;
  return (
    <div className="flex flex-col gap-1">
      <p>
        <span className="font-medium">{OUTCOME_LABEL[decision.outcome]}</span>
      </p>
      <p className="text-meta text-muted">
        {`${decision.approver.name} · v${String(decision.version_n)} · ${formatDate(decision.decided_at)}`}
      </p>
      <p className="app-drawer-quote">{decision.reason}</p>
    </div>
  );
}

function NotesField({ item, editable }: { item: ItemDetailOut; editable: boolean }) {
  const [value, setValue] = useState(item.notes);
  const patch = useItemPatch();

  if (!editable) {
    return (
      <div className="app-drawer-section">
        <h3 className="app-drawer-label">Notes</h3>
        <p className={item.notes === '' ? 'text-muted' : 'whitespace-pre-wrap'}>
          {item.notes === '' ? 'No notes' : item.notes}
        </p>
      </div>
    );
  }
  return (
    <TextField
      className="app-drawer-section"
      value={value}
      onChange={setValue}
      onBlur={() => {
        if (value !== item.notes) patch.mutate({ itemId: item.id, data: { notes: value } });
      }}
    >
      <Label className="app-drawer-label">Notes</Label>
      <TextArea className="app-textarea" placeholder="Visible to reviewers and the submitter" rows={3} />
    </TextField>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="app-drawer-fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function DrawerBody({
  item,
  viewer,
  onOpenReview,
}: {
  item: ItemDetailOut;
  viewer: Viewer;
  onOpenReview: (id: number) => void;
}) {
  const editable = canEditFields(viewer, item);
  const patch = useItemPatch();
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return; // new tab/window
    event.preventDefault();
    onOpenReview(item.id);
  };

  return (
    <>
      <div className="app-drawer-body">
        <h2 id={PREVIEW_HEADING_ID} tabIndex={-1} className="app-drawer-title">
          {item.title}
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={item.status} />
          <RiskTierBadge tier={item.risk_tier} />
          {item.reopen_reason !== null && (
            <span className="app-drawer-reopen">{`Re-review: ${REOPEN_REASON_LABEL[item.reopen_reason]}`}</span>
          )}
          {item.is_legacy && <span className="app-tag">Legacy</span>}
        </div>
        <a
          href={reviewPath(item.id)}
          onClick={open}
          className="app-btn app-drawer-open"
          data-variant="primary"
        >
          <Icon name="action.open_external" size={16} />
          Open review
          <Kbd keys={['o']} />
        </a>

        <div className="app-drawer-section">
          <h3 className="app-drawer-label">Open findings</h3>
          <FindingsSummary itemId={item.id} fallback={item.open_findings_count} />
        </div>

        <div className="app-drawer-section">
          <h3 className="app-drawer-label">Latest decision</h3>
          <LatestDecision decision={item.latest_decision} />
        </div>

        <dl className="app-drawer-facts">
          <Fact label="Product">{PRODUCT_LABEL[item.product]}</Fact>
          <Fact label="Channel">{CHANNEL_LABEL[item.channel]}</Fact>
          <Fact label="Partner">{item.partner?.name ?? '—'}</Fact>
          <Fact label="Submitted by">{item.owner?.name ?? (item.legacy_submitter || '—')}</Fact>
          <Fact label="Assignee">{item.assignee?.name ?? 'Unassigned'}</Fact>
          <Fact label="Round">{`${roundLabel(item.round)} · v${String(item.current_version_n ?? 1)}`}</Fact>
          <Fact label="Submitted">
            <span className="inline-flex items-center gap-1.5">
              {formatDate(item.submitted_at)} <RelativeAge at={item.submitted_at} />
            </span>
          </Fact>
          <Fact label="Planned run">{runDates(item)}</Fact>
          <Fact label="Markets">{item.markets.length > 0 ? item.markets.join(', ') : '—'}</Fact>
          {item.risk_tier_overridden && canEditRisk(viewer) && (
            <Fact label="Risk">Overridden by a reviewer</Fact>
          )}
        </dl>

        {/* Keyed so a saved (or remotely changed) note resets the field instead of syncing state in an effect. */}
        <NotesField key={`${String(item.id)}:${item.notes}`} item={item} editable={editable} />

        <div className="app-drawer-section">
          <h3 className="app-drawer-label">Tags</h3>
          {editable ? (
            <TagEditor
              tags={item.tags}
              autoFocus={false}
              onChange={(tags) => {
                patch.mutate({ itemId: item.id, data: { tags } });
              }}
            />
          ) : item.tags.length > 0 ? (
            <span className="app-tags flex-wrap">
              {item.tags.map((t) => (
                <span key={t} className="app-tag">
                  {t}
                </span>
              ))}
            </span>
          ) : (
            <p className="text-muted">No tags</p>
          )}
        </div>
      </div>
    </>
  );
}

function DrawerSkeleton() {
  return (
    <div className="app-drawer-body" aria-busy="true" aria-label="Loading item">
      <SkeletonText width="80%" />
      <SkeletonText width="40%" />
      <span className="app-skeleton h-8 w-36" />
      <SkeletonText width="60%" />
      <SkeletonText width="70%" />
      <SkeletonText width="50%" />
    </div>
  );
}

export interface PreviewDrawerProps {
  itemId: number;
  viewer: Viewer;
  onClose: () => void;
  onOpenReview: (id: number) => void;
  /** Move focus into the drawer (opened with Enter): the panel at once, its heading once the item loads. */
  autoFocus?: boolean;
}

export function PreviewDrawer({
  itemId,
  viewer,
  onClose,
  onOpenReview,
  autoFocus = false,
}: PreviewDrawerProps) {
  const item = useGetItem(itemId);
  const key = item.data?.key ?? `CP-${String(itemId)}`;
  const panel = useRef<HTMLElement>(null);
  const loaded = item.data !== undefined;

  useEffect(() => {
    if (!autoFocus) return;
    if (loaded) document.getElementById(PREVIEW_HEADING_ID)?.focus();
    else panel.current?.focus();
  }, [autoFocus, loaded]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Escape') return;
    const target = event.target as HTMLElement;
    if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
      target.blur(); // leaving a field saves it; a second Escape closes
      return;
    }
    onClose();
  };

  return (
    <aside
      ref={panel}
      tabIndex={-1}
      className="app-drawer"
      aria-label={`Preview ${key}`}
      onKeyDown={onKeyDown}
    >
      <div className="app-drawer-head">
        <ItemKey value={key} />
        <IconButton icon="action.close" size="sm" aria-label="Close preview" onPress={onClose} />
      </div>
      {item.isPending ? (
        <DrawerSkeleton />
      ) : item.isError ? (
        <div className="app-drawer-body">
          {errorStatus(item.error) === 404 ? (
            <p>{`${key} no longer exists.`}</p>
          ) : (
            <div className="flex flex-col items-start gap-2" role="alert">
              <p>{errorMessage(item.error, `Couldn't load ${key}.`)}</p>
              <Button
                size="sm"
                icon="action.reload"
                onPress={() => {
                  void item.refetch();
                }}
              >
                Retry
              </Button>
            </div>
          )}
        </div>
      ) : (
        <DrawerBody item={item.data} viewer={viewer} onOpenReview={onOpenReview} />
      )}
    </aside>
  );
}
