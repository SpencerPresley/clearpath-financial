import type { UseQueryResult } from '@tanstack/react-query';

import type { FindingOut, ItemDetailOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { groupFindings } from '../../ui/findings/groupFindings';
import type { LiveEditor } from '../../ui/findings/LiveFindings';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { SkeletonBadge, SkeletonText } from '../../ui/Skeleton';
import { FindingCard } from './FindingCard';
import { LlmStatus } from './LlmStatus';

export interface FindingsPanelProps {
  item: ItemDetailOut;
  findings: UseQueryResult<FindingOut[], unknown>;
  shownN: number;
  viewingCurrent: boolean;
  canTriage: boolean;
  /** Reviewer or lead: gets the copy about approving. */
  isDecider: boolean;
  isMarketer: boolean;
  /** Approve with edits is open: findings with a literal fix offer Apply into the reviewer's edit. */
  editor?: LiveEditor;
  activeId: number | null;
  dismissingId: number | null;
  pendingId: number | undefined;
  onActivate: (id: number) => void;
  onAccept: (id: number) => void;
  onStartDismiss: (id: number) => void;
  onCancelDismiss: () => void;
  onDismiss: (id: number, reason: string) => void;
  onReopen: (id: number) => void;
}

function FindingsSkeleton() {
  return (
    <div role="status" aria-label="Loading findings" className="app-findings">
      {[0, 1, 2].map((row) => (
        <div key={row} className="app-finding-card" aria-hidden="true">
          <div className="app-finding-tags">
            <SkeletonBadge />
            <SkeletonText width="5rem" />
          </div>
          <SkeletonText width={`${String(70 + row * 8)}%`} />
          <SkeletonText width="40%" />
        </div>
      ))}
    </div>
  );
}

export function FindingsPanel(props: FindingsPanelProps) {
  const { item, findings, shownN, viewingCurrent, canTriage, activeId, dismissingId, pendingId } = props;

  const status = viewingCurrent ? (
    <LlmStatus
      item={item}
      aiCount={(findings.data ?? []).filter((f) => f.source === 'llm').length}
      canRetry={canTriage}
      isDecider={props.isDecider}
      isMarketer={props.isMarketer}
    />
  ) : null;

  if (findings.isPending) {
    return (
      <>
        {status}
        <FindingsSkeleton />
      </>
    );
  }
  if (findings.isError) {
    return (
      <>
        {status}
        <div className="app-inline-error" role="alert">
          <span>Findings didn’t load. {apiErrorMessage(findings.error)}</span>
          <Button
            size="sm"
            onPress={() => {
              void findings.refetch();
            }}
          >
            Retry
          </Button>
        </div>
      </>
    );
  }

  const groups = groupFindings(findings.data);
  return (
    <>
      {status}
      {groups.length === 0 ? (
        <EmptyState icon="entity.finding" title={`No findings on v${String(shownN)}`}>
          Code checks found nothing to flag
          {item.llm_check_status === 'succeeded' ? ' and the AI check had no suggestions' : ''}.
          {props.isDecider ? ' Review the copy and decide.' : ''}
        </EmptyState>
      ) : (
        <div className="app-findings">
          {groups.map((group) => {
            const open = group.findings.filter((f) => f.state === 'open').length;
            return (
              <section key={group.id} aria-labelledby={`group-${group.id}`} className="app-finding-group">
                <h3 id={`group-${group.id}`} className="app-finding-group-title">
                  {group.label}
                  <span className="app-finding-group-count">
                    {open === 0 ? 'all triaged' : `${String(open)} open of ${String(group.findings.length)}`}
                  </span>
                </h3>
                {group.findings.map((finding) => (
                  <FindingCard
                    key={finding.id}
                    finding={finding}
                    active={finding.id === activeId}
                    canTriage={canTriage}
                    dismissing={finding.id === dismissingId}
                    pending={finding.id === pendingId}
                    editor={props.editor}
                    onActivate={() => {
                      props.onActivate(finding.id);
                    }}
                    onAccept={() => {
                      props.onAccept(finding.id);
                    }}
                    onStartDismiss={() => {
                      props.onStartDismiss(finding.id);
                    }}
                    onCancelDismiss={props.onCancelDismiss}
                    onDismiss={(reason) => {
                      props.onDismiss(finding.id, reason);
                    }}
                    onReopen={() => {
                      props.onReopen(finding.id);
                    }}
                  />
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
