import { Link } from '@tanstack/react-router';
import { useEffect, useMemo, useState } from 'react';
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components';

import type { CheckPreviewIn, FindingOut, ItemDetailOut } from '../../api/generated/model';
import { ApiError } from '../../api/mutator';
import { Button } from '../../ui/Button';
import { useLiveChecks } from '../../ui/copy/useLiveChecks';
import { EmptyState } from '../../ui/EmptyState';
import { flattenGroups, groupFindings } from '../../ui/findings/groupFindings';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { useViewer } from '../../ui/layout/Viewer';
import { SkeletonBadge, SkeletonText } from '../../ui/Skeleton';
import { showToast } from '../../ui/toast';
import { useHotkeys } from '../../ui/useHotkeys';
import { CopyPane } from './CopyPane';
import { DecisionBar } from './DecisionBar';
import { DecisionPanel } from './DecisionPanel';
import type { DecisionMode } from './decisionModes';
import { findingCardId } from './FindingCard';
import { FindingsPanel } from './FindingsPanel';
import { decisionGate } from './gate';
import type { ReviewSearch, ReviewTab } from './reviewSearch';
import { ShortcutsDialog } from './ShortcutsDialog';
import { StatusNote } from './StatusNote';
import { CommentsTab, DetailsTab, EvidenceTab, HistoryTab } from './tabs';
import { useReviewData } from './useReviewData';
import { useTriage } from './useTriage';

export interface ReviewPageProps {
  itemId: number;
  search: ReviewSearch;
  onSearchChange: (next: Partial<ReviewSearch>) => void;
}

const TRIAGE_STATUSES: readonly ItemDetailOut['status'][] = ['submitted', 'in_review', 'needs_rereview'];

function ReviewSkeleton() {
  return (
    <div className="app-review" role="status" aria-label="Loading item" aria-busy="true">
      <div className="app-decision-bar" aria-hidden="true">
        <div className="app-decision-bar-heading">
          <SkeletonText width="4rem" />
          <SkeletonText width="18rem" />
        </div>
        <div className="app-decision-bar-meta">
          <SkeletonBadge />
          <SkeletonBadge />
        </div>
      </div>
      <div className="app-review-body" aria-hidden="true">
        <div className="app-review-center">
          <div className="app-copy-skeleton">
            {['92%', '84%', '96%', '60%'].map((w) => (
              <SkeletonText key={w} width={w} />
            ))}
          </div>
        </div>
        <div className="app-review-panel" />
      </div>
    </div>
  );
}

function scrollToFinding(id: number) {
  const card = document.getElementById(findingCardId(id));
  card?.focus({ preventScroll: true });
  for (const el of [card, document.querySelector(`[data-mark-ids~="${String(id)}"]`)]) {
    if (el !== null && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }
}

export function ReviewPage({ itemId, search, onSearchChange }: ReviewPageProps) {
  const viewer = useViewer();
  const isDecider = viewer.roles.some((role) => role === 'reviewer' || role === 'lead');
  const data = useReviewData(itemId, search.v);
  const item = data.item.data;

  const [activeId, setActiveId] = useState<number | null>(null);
  const [focusRequest, setFocusRequest] = useState(0);
  const [dismissingId, setDismissingId] = useState<number | null>(null);
  const [mode, setMode] = useState<DecisionMode | null>(null);
  const [editText, setEditText] = useState('');
  const [showEditDiff, setShowEditDiff] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const tab: ReviewTab = search.tab ?? 'findings';
  const findings: FindingOut[] = useMemo(() => data.findings.data ?? [], [data.findings.data]);
  const ordered = useMemo(() => flattenGroups(groupFindings(findings)), [findings]);
  const shownN = data.shownN ?? 0;
  const triage = useTriage(itemId, data.shownN);

  const gate = decisionGate(
    item ?? { status: 'draft', llm_check_status: 'pending', current_version_n: null },
    findings,
    shownN,
  );
  const canTriage =
    item !== undefined && isDecider && data.viewingCurrent && TRIAGE_STATUSES.includes(item.status);

  // Approve with edits: the reviewer's draft gets the same live code checks as intake.
  // A reviewer-edit current version in review means the reviewer's v+1 came back with findings to triage;
  // Approve with edits then re-approves it as is (no new editor).
  const reapprovingEdit = item?.current_version?.origin === 'reviewer_edit';
  const editing = mode === 'approved_with_edits' && item !== undefined && !reapprovingEdit;
  const liveInput: CheckPreviewIn | null =
    editing && item.current_version !== null
      ? {
          content_text: editText,
          product: item.product,
          channel: item.channel,
          markets: item.markets,
          partner_id: item.partner?.id ?? null,
          is_prescreen: item.is_prescreen,
          attachment_kinds: (data.attachments.data ?? []).map((a) => a.kind),
        }
      : null;
  const live = useLiveChecks(liveInput);

  useEffect(() => {
    if (activeId !== null && focusRequest > 0) {
      scrollToFinding(activeId);
    }
  }, [activeId, focusRequest]);

  const activate = (id: number) => {
    setActiveId(id);
    if (tab !== 'findings') onSearchChange({ tab: 'findings' });
    setFocusRequest((n) => n + 1);
  };
  const step = (delta: 1 | -1) => {
    if (ordered.length === 0) return;
    const index = ordered.findIndex((f) => f.id === activeId);
    const next =
      index === -1
        ? delta === 1
          ? 0
          : ordered.length - 1
        : (index + delta + ordered.length) % ordered.length;
    const target = ordered[next];
    if (target !== undefined) activate(target.id);
  };
  const active = ordered.find((f) => f.id === activeId);
  // After a keyboard triage, move to the next open finding so each finding takes one key.
  const advanceFrom = (id: number) => {
    const index = ordered.findIndex((f) => f.id === id);
    const rest = [...ordered.slice(index + 1), ...ordered.slice(0, index)];
    const next = rest.find((f) => f.state === 'open');
    if (next !== undefined) activate(next.id);
  };
  const openMode = (next: DecisionMode) => {
    if (next === 'approved_with_edits' && item?.current_version && !reapprovingEdit) {
      setEditText(item.current_version.content_text);
      setShowEditDiff(false);
    }
    setMode((current) => (current === next ? null : next));
  };

  useHotkeys(
    {
      n: () => {
        step(1);
      },
      p: () => {
        step(-1);
      },
      a: () => {
        if (canTriage && active?.state === 'open') {
          triage.accept(active.id);
          advanceFrom(active.id);
        }
      },
      d: () => {
        if (canTriage && active?.state === 'open') {
          if (tab !== 'findings') onSearchChange({ tab: 'findings' });
          setDismissingId(active.id);
        }
      },
      e: () => {
        if (isDecider && gate.canDecide && mode !== 'approved_with_edits') openMode('approved_with_edits');
      },
      '?': () => {
        setShortcutsOpen(true);
      },
      Escape: () => {
        if (dismissingId !== null) setDismissingId(null);
        else if (mode !== null) setMode(null);
      },
    },
    item !== undefined,
  );

  if (data.item.isPending) {
    return <ReviewSkeleton />;
  }
  if (data.item.isError || item === undefined) {
    const notFound = data.item.error instanceof ApiError && data.item.error.status === 404;
    return (
      <div className="app-review-error">
        {notFound ? (
          <EmptyState
            icon="entity.item"
            title={`CP-${String(itemId)} not found`}
            action={
              <Link to="/" className="app-link">
                Back to the queue
              </Link>
            }
          >
            It may have been deleted, or the link has a typo.
          </EmptyState>
        ) : (
          <div className="app-inline-error" role="alert">
            <span>This item didn’t load. {apiErrorMessage(data.item.error)}</span>
            <Button
              size="sm"
              onPress={() => {
                void data.item.refetch();
              }}
            >
              Retry
            </Button>
          </div>
        )}
      </div>
    );
  }

  const openCount = findings.filter((f) => f.state === 'open').length;

  return (
    <div className="app-review">
      <div className="app-review-top">
        <DecisionBar
          item={item}
          gate={gate}
          isDecider={isDecider}
          mode={mode}
          onMode={openMode}
          onShortcuts={() => {
            setShortcutsOpen(true);
          }}
          onCheckQueued={() => {
            onSearchChange({ tab: 'details' });
          }}
        />
        {mode !== null && (
          <DecisionPanel
            key={mode}
            item={item}
            mode={mode}
            gate={gate}
            findings={findings}
            attachments={data.attachments.data ?? []}
            editedText={editing ? editText : undefined}
            onCancel={() => {
              setMode(null);
            }}
            onDone={() => {
              setMode(null);
              onSearchChange({ v: undefined, compare: undefined });
            }}
            onNeedsTriage={(message) => {
              setMode(null);
              setActiveId(null);
              onSearchChange({ v: undefined, compare: undefined, tab: undefined });
              showToast({ title: 'Your edit has new findings', description: message });
            }}
          />
        )}
      </div>
      <div className="app-review-body">
        <div className="app-review-center-wrap">
          <StatusNote
            item={item}
            viewingCurrent={data.viewingCurrent}
            shownN={shownN}
            onShowCurrent={() => {
              onSearchChange({ v: undefined, compare: undefined });
            }}
            compareN={search.compare}
            onCompareApproved={(approvedN) => {
              onSearchChange({ v: undefined, compare: approvedN });
            }}
          />
          <CopyPane
            item={item}
            version={data.version}
            versionLoading={data.versionLoading}
            shownN={shownN}
            compareN={search.compare}
            findings={findings}
            activeId={activeId}
            attachments={data.attachments.data ?? []}
            onActivate={activate}
            onVersionChange={(n) => {
              onSearchChange({ v: n === data.currentN ? undefined : n, compare: undefined });
              setActiveId(null);
            }}
            onCompareChange={(n) => {
              onSearchChange({ compare: n });
            }}
            edit={
              editing
                ? {
                    text: editText,
                    onChange: setEditText,
                    marks: live.marks,
                    findings: live.findings,
                    checking: live.status === 'checking',
                    showDiff: showEditDiff,
                    onShowDiffChange: setShowEditDiff,
                  }
                : undefined
            }
          />
        </div>
        <Tabs
          className="app-review-panel"
          selectedKey={tab}
          onSelectionChange={(key) => {
            onSearchChange({ tab: key === 'findings' ? undefined : (String(key) as ReviewTab) });
          }}
        >
          <TabList aria-label="Item details" className="app-tabs">
            <Tab id="findings" className="app-tab">
              Findings
              {openCount > 0 && (
                <span className="app-tab-count app-figure" aria-label={`${String(openCount)} open`}>
                  {openCount}
                </span>
              )}
            </Tab>
            <Tab id="comments" className="app-tab">
              Comments
            </Tab>
            <Tab id="details" className="app-tab">
              Details
            </Tab>
            <Tab id="evidence" className="app-tab">
              Evidence
              {(data.attachments.data?.length ?? 0) > 0 && (
                <span className="app-tab-count app-figure">{data.attachments.data?.length}</span>
              )}
            </Tab>
            <Tab id="history" className="app-tab">
              History
            </Tab>
          </TabList>
          <TabPanel id="findings" className="app-tab-panel">
            <FindingsPanel
              item={item}
              findings={data.findings}
              shownN={shownN}
              viewingCurrent={data.viewingCurrent}
              canTriage={canTriage}
              activeId={activeId}
              dismissingId={dismissingId}
              pendingId={triage.pendingId}
              onActivate={(id) => {
                setActiveId(id);
              }}
              onAccept={(id) => {
                setActiveId(id);
                triage.accept(id);
              }}
              onStartDismiss={(id) => {
                setActiveId(id);
                setDismissingId(id);
              }}
              onCancelDismiss={() => {
                setDismissingId(null);
              }}
              onDismiss={(id, reason) => {
                triage.dismiss(id, reason, () => {
                  setDismissingId(null);
                  advanceFrom(id);
                });
              }}
              onReopen={(id) => {
                triage.reopen(id);
              }}
            />
          </TabPanel>
          <TabPanel id="comments" className="app-tab-panel">
            <CommentsTab itemId={item.id} versionN={shownN} canComment />
          </TabPanel>
          <TabPanel id="details" className="app-tab-panel">
            <DetailsTab item={item} />
          </TabPanel>
          <TabPanel id="evidence" className="app-tab-panel">
            <EvidenceTab
              itemId={item.id}
              attachments={data.attachments.data ?? []}
              loading={data.attachments.isPending}
              canUpload
            />
          </TabPanel>
          <TabPanel id="history" className="app-tab-panel">
            <HistoryTab item={item} />
          </TabPanel>
        </Tabs>
      </div>
      <ShortcutsDialog isOpen={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}
