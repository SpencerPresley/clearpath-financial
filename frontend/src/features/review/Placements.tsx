/*
 * Where the approved content runs, and what the drift monitor last saw there (product-spec "Drift monitoring").
 * Each placement with a web address shows its latest check: unchanged, changed (with the diff against the approved
 * version), copy missing, or a failed check with its reason, plus the code checks run on the whole page. Unchanged
 * copy with new blocking findings beside it is flagged (attention; the item stays approved), and a page that can't be
 * fetched on repeated checks counts as copy missing once it sends the item to re-review. "Check
 * now" queues a check and the panel polls until it lands; a check that sends the item to re-review refreshes the
 * item. On the demo partner pages a lead or admin can simulate the partner's edit (demo only).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { getGetItemHistoryQueryKey, getGetItemQueryKey } from '../../api/generated/items/items';
import {
  getGetItemDriftQueryKey,
  useCheckPlacementDrift,
  useGetItemDrift,
} from '../../api/generated/drift/drift';
import { useSetDemoPageEdited } from '../../api/generated/demo/demo';
import type { ItemDriftOut, PlacementDriftOut, SnapshotOut } from '../../api/generated/model';
import type { Tone } from '../../ui/badges';
import { SeverityBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { DiffText } from '../../ui/copy/DiffText';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import type { IconKey } from '../../ui/icons';
import { plural } from '../../ui/labels';
import { useViewer } from '../../ui/layout/Viewer';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonText } from '../../ui/Skeleton';

/** While a check is queued or running, the drift read is polled so the result arrives without a reload. */
export const DRIFT_POLL_MS = 2000;

const isInFlight = (snapshot: SnapshotOut | null) =>
  snapshot !== null && (snapshot.status === 'pending' || snapshot.status === 'running');

export function anyCheckInFlight(data: ItemDriftOut | undefined): boolean {
  return data?.placements.some((p) => isInFlight(p.latest)) ?? false;
}

interface Outcome {
  label: string;
  tone: Tone;
  icon: IconKey;
}

export function checkOutcome(snapshot: SnapshotOut): Outcome {
  if (isInFlight(snapshot)) return { label: 'Checking the page…', tone: 'info', icon: 'action.reload' };
  // A failed check that reopened the item: consecutive checks couldn't fetch the page, so the copy counts as missing.
  if (snapshot.status === 'failed' && snapshot.reopened_item) {
    return { label: 'Page unreachable', tone: 'alert', icon: 'drift.missing' };
  }
  if (snapshot.status === 'failed') return { label: 'Check failed', tone: 'error', icon: 'feedback.error' };
  switch (snapshot.result) {
    case 'unchanged':
      return { label: 'Unchanged', tone: 'success', icon: 'drift.unchanged' };
    case 'modified':
      return { label: 'Changed on the page', tone: 'alert', icon: 'drift.modified' };
    default:
      return { label: 'Copy missing', tone: 'alert', icon: 'drift.missing' };
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** host + path, without the scheme or a trailing slash: enough to tell two pages on one site apart. */
export function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.host}${parsed.pathname}`.replace(/\/$/, '');
  } catch {
    return url;
  }
}

/** Partner text beside intact approved copy that trips blocking rules: nothing reopens, so it's flagged here. */
export function needsAttention(snapshot: SnapshotOut): boolean {
  return snapshot.result === 'unchanged' && snapshot.new_blocking_count > 0;
}

function FailedNote({ snapshot, failureStreak }: { snapshot: SnapshotOut; failureStreak: number }) {
  if (snapshot.reopened_item) {
    return (
      <p className="app-drift-note">
        {plural(failureStreak, 'daily check')} in a row couldn’t fetch the page, so the approved copy counts
        as missing.
      </p>
    );
  }
  const streak =
    failureStreak > 1 ? ` ${plural(failureStreak, 'daily check')} in a row couldn’t fetch the page.` : '';
  return (
    <p className="app-drift-note">
      {snapshot.error_message ?? 'The page could not be checked.'}
      {streak} Nothing changed on the item.
    </p>
  );
}

function LastCheck({ snapshot, failureStreak }: { snapshot: SnapshotOut; failureStreak: number }) {
  const outcome = checkOutcome(snapshot);
  const attention = needsAttention(snapshot);
  const against =
    snapshot.compared_version_n === null ? '' : ` against v${String(snapshot.compared_version_n)}`;
  const who = snapshot.requested_by === null ? 'Daily check' : `Checked by ${snapshot.requested_by.name}`;
  return (
    <div className="app-drift-check">
      <p className="app-drift-check-line">
        <span className="app-badge" data-tone={outcome.tone}>
          <Icon name={outcome.icon} size={14} />
          <span>{outcome.label}</span>
        </span>
        {attention && (
          <span className="app-badge" data-tone="alert">
            <Icon name="severity.blocking" size={14} />
            <span>New blocking findings</span>
          </span>
        )}
        {!isInFlight(snapshot) && (
          <span className="app-timeline-meta">
            {who}
            {against} · <RelativeAge at={snapshot.finished_at ?? snapshot.requested_at} />
          </span>
        )}
      </p>
      {snapshot.reopened_item && <p className="app-drift-note">This check sent the item to re-review.</p>}
      {snapshot.status === 'failed' && <FailedNote snapshot={snapshot} failureStreak={failureStreak} />}
      {attention && (
        <p className="app-drift-note">
          The approved copy is intact, but text beside it has{' '}
          {plural(snapshot.new_blocking_count, 'new blocking finding')}. The item stays approved.
        </p>
      )}
      {snapshot.result === 'missing' && (
        <p className="app-drift-note">
          The approved copy wasn’t found on {hostOf(snapshot.final_url ?? snapshot.url)}
          {snapshot.score === null
            ? ''
            : ` (closest match keeps ${String(Math.round(snapshot.score))}% of it)`}
          .
        </p>
      )}
      {snapshot.result === 'modified' && (
        <div className="app-drift-diff">
          <p className="app-field-label">
            Approved v{String(snapshot.compared_version_n ?? '')} compared with the page
          </p>
          <DiffText segments={snapshot.diff} />
        </div>
      )}
      {snapshot.findings.length > 0 && <PageFindings snapshot={snapshot} />}
    </div>
  );
}

function PageFindings({ snapshot }: { snapshot: SnapshotOut }) {
  const fresh = snapshot.findings.filter((f) => f.new).length;
  return (
    <details className="app-drift-findings" open={fresh > 0}>
      <summary>
        Code checks on the whole page: {snapshot.findings.length}
        {fresh > 0 ? `, ${String(fresh)} not on the approved copy` : ''}
      </summary>
      <ul className="app-plain-list">
        {snapshot.findings.map((finding, index) => (
          <li key={`${finding.rule_id}-${String(index)}`} className="app-drift-finding">
            <SeverityBadge severity={finding.severity} />
            <span className="app-drift-finding-text">
              <span>{finding.message}</span>
              {finding.quote !== null && <q className="app-drift-quote">{finding.quote}</q>}
              {finding.new && <span className="app-drift-new">New on the page</span>}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function PlacementRow({
  itemId,
  placement,
  canCheck,
  canSimulate,
}: {
  itemId: number;
  placement: PlacementDriftOut;
  canCheck: boolean;
  canSimulate: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: getGetItemDriftQueryKey(itemId) });
  const check = useCheckPlacementDrift({
    mutation: {
      onSuccess: () => {
        setError(null);
        void refresh();
      },
      onError: (e) => {
        setError(apiErrorMessage(e));
      },
    },
  });
  const simulate = useSetDemoPageEdited({
    mutation: {
      onSuccess: () => void refresh(),
      onError: (e) => {
        setError(apiErrorMessage(e));
      },
    },
  });
  const inFlight = isInFlight(placement.latest);
  const demo = placement.demo_page;

  return (
    <li className="app-placement">
      <div className="app-placement-head">
        <p className="app-placement-location">{placement.location}</p>
        <a href={placement.url} className="app-link" target="_blank" rel="noopener noreferrer">
          {displayUrl(placement.url)}
          <Icon name="action.open_external" size={14} />
        </a>
        <p className="app-timeline-meta">
          {placement.is_live ? 'Live' : 'Not live'} ·{' '}
          {placement.monitored ? 'Checked daily' : 'Not monitored'}
        </p>
      </div>
      {placement.latest === null ? (
        <p className="app-muted">Not checked yet.</p>
      ) : (
        <LastCheck snapshot={placement.latest} failureStreak={placement.failure_streak} />
      )}
      {error !== null && (
        <p className="app-field-error" role="alert">
          {error}
        </p>
      )}
      {(canCheck || (demo !== null && canSimulate)) && (
        <div className="app-placement-actions">
          {canCheck && (
            <Button
              size="sm"
              icon="action.reload"
              isPending={inFlight || check.isPending}
              onPress={() => {
                check.mutate({ placementId: placement.placement_id });
              }}
            >
              Check now
            </Button>
          )}
          {demo !== null && canSimulate && (
            <>
              <Button
                size="sm"
                variant="ghost"
                icon="action.edit"
                isPending={simulate.isPending}
                onPress={() => {
                  simulate.mutate({ slug: demo.slug, data: { edited: !demo.edited } });
                }}
              >
                {demo.edited ? 'Restore original page' : 'Simulate partner edit'}
              </Button>
              <span className="app-badge" data-tone="neutral">
                Demo
              </span>
              <span className="app-timeline-meta">
                {demo.edited ? `Showing the edited page. ${demo.edit_summary}` : demo.edit_summary}
              </span>
            </>
          )}
        </div>
      )}
    </li>
  );
}

export function PlacementsSection({ itemId, ownerId }: { itemId: number; ownerId: number | null }) {
  const viewer = useViewer();
  const queryClient = useQueryClient();
  const drift = useGetItemDrift(itemId, {
    query: { refetchInterval: (query) => (anyCheckInFlight(query.state.data) ? DRIFT_POLL_MS : false) },
  });

  // A check that just landed may have sent the item to re-review: refresh the item and its history.
  const wasInFlight = useRef(false);
  const inFlight = anyCheckInFlight(drift.data);
  useEffect(() => {
    if (wasInFlight.current && !inFlight) {
      void queryClient.invalidateQueries({ queryKey: getGetItemQueryKey(itemId) });
      void queryClient.invalidateQueries({ queryKey: getGetItemHistoryQueryKey(itemId) });
    }
    wasInFlight.current = inFlight;
  }, [inFlight, itemId, queryClient]);

  const canCheck =
    viewer.id === ownerId || viewer.roles.some((r) => r === 'reviewer' || r === 'lead' || r === 'admin');
  const canSimulate = viewer.roles.some((r) => r === 'lead' || r === 'admin');

  return (
    <section aria-labelledby="placements-title">
      <h3 id="placements-title" className="app-panel-heading">
        Where it runs
      </h3>
      {drift.isPending ? (
        <div role="status" aria-label="Loading placements" className="app-panel-skeleton">
          <SkeletonText width="60%" />
          <SkeletonText width="80%" />
        </div>
      ) : drift.isError ? (
        <div className="app-inline-error" role="alert">
          <span>Placements didn’t load. {apiErrorMessage(drift.error)}</span>
          <Button size="sm" onPress={() => void drift.refetch()}>
            Retry
          </Button>
        </div>
      ) : drift.data.placements.length === 0 ? (
        <p className="app-muted">No placements with a web address. Placements are recorded after approval.</p>
      ) : (
        <ul className="app-placement-list">
          {drift.data.placements.map((placement) => (
            <PlacementRow
              key={placement.placement_id}
              itemId={itemId}
              placement={placement}
              canCheck={canCheck}
              canSimulate={canSimulate}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
