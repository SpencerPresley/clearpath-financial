/*
 * The partner detail's main column: items (every status, legacy imports marked), the findings history across
 * every version of those items, and the rules that keep firing (repeat issues). Each loads and fails on its
 * own, so a failed history leaves the rest of the page working (spec §5.5 partial state).
 */
import { Link } from '@tanstack/react-router';
import type { ReactNode } from 'react';

import type { PartnerDetailOut } from '../../api/generated/model';
import { SeverityBadge, SourceTag, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { ItemKey } from '../../ui/ItemKey';
import { CHANNEL_LABELS, FINDING_STATE_LABELS, formatDate, plural } from '../../ui/labels';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonTable } from '../../ui/Skeleton';
import { usePartnerFindings, usePartnerItems } from './pages';

function SectionError({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <div className="app-inline-error" role="alert">
      <span>
        {what} didn&apos;t load. {apiErrorMessage(error)}
      </span>
      <Button size="sm" onPress={onRetry}>
        Retry
      </Button>
    </div>
  );
}

function LoadMore({
  hasMore,
  loading,
  failed,
  onLoad,
  shown,
}: {
  hasMore: boolean;
  loading: boolean;
  failed: unknown;
  onLoad: () => void;
  shown: string;
}) {
  return (
    <div className="app-tp-footer">
      <span className="app-muted app-figure">{shown}</span>
      {failed !== null && <span className="app-form-error">{apiErrorMessage(failed)}</span>}
      {hasMore && (
        <Button size="sm" isDisabled={loading} onPress={onLoad}>
          {loading ? 'Loading…' : 'Load more'}
        </Button>
      )}
    </div>
  );
}

// ---- Items -----------------------------------------------------------------------------------------

/** Key, title, status, channel, open findings, submitted. */
const ITEM_COLUMNS = ['6.5rem', 'auto', '9rem', '8.5rem', '4.5rem', '7rem'] as const;

export function PartnerItems({ partner }: { partner: PartnerDetailOut }) {
  const { query, rows } = usePartnerItems(partner.id);

  if (query.isPending) {
    return (
      <SkeletonTable
        rows={5}
        columns={ITEM_COLUMNS.map((w) => (w === 'auto' ? '1fr' : w))}
        label="Loading items"
      />
    );
  }
  if (query.isError && rows.length === 0) {
    return (
      <SectionError
        what="Items"
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (rows.length === 0) {
    return (
      <EmptyState icon="entity.item" title={`No items from ${partner.name} yet`}>
        Items submitted on an affiliate channel with this partner show here, with imported tracker rows.
      </EmptyState>
    );
  }
  return (
    <>
      <div className="app-tp-table-wrap">
        <table className="app-tp-table" aria-label={`Items from ${partner.name}`}>
          <colgroup>
            {ITEM_COLUMNS.map((width, index) => (
              <col key={index} style={width === 'auto' ? undefined : { width }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Title</th>
              <th scope="col">Status</th>
              <th scope="col">Channel</th>
              <th scope="col" className="app-tp-num">
                Findings
              </th>
              <th scope="col" className="app-tp-num">
                Submitted
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id}>
                <td>
                  <ItemKey value={item.key} />
                </td>
                <td className="app-tp-cell-title">
                  <Link to="/items/$itemId" params={{ itemId: String(item.id) }} className="app-tp-link">
                    {item.title}
                  </Link>
                  {item.is_legacy && (
                    <span className="app-tag app-tp-legacy" title="Imported from the tracker: metadata only">
                      Legacy
                    </span>
                  )}
                </td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
                <td className="app-muted">{CHANNEL_LABELS[item.channel]}</td>
                <td className="app-tp-num">{item.is_legacy ? '—' : item.open_findings_count}</td>
                <td className="app-tp-num app-muted">{formatDate(item.submitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <LoadMore
        shown={`${plural(rows.length, 'item')} shown`}
        hasMore={query.hasNextPage}
        loading={query.isFetchingNextPage}
        failed={query.isFetchNextPageError ? query.error : null}
        onLoad={() => {
          void query.fetchNextPage();
        }}
      />
    </>
  );
}

// ---- Findings history ---------------------------------------------------------------------------------

export function FindingsHistory({ partner }: { partner: PartnerDetailOut }) {
  const { query, rows } = usePartnerFindings(partner.id);

  if (query.isPending) {
    return <SkeletonTable rows={5} columns={['1fr', '12rem', '6rem']} label="Loading findings history" />;
  }
  if (query.isError && rows.length === 0) {
    return (
      <SectionError
        what="Findings history"
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  if (rows.length === 0) {
    return (
      <EmptyState icon="entity.finding" title={`No findings on ${partner.name}'s items`}>
        Code checks, AI suggestions, and checklist items on any version of this partner&apos;s content show
        here.
      </EmptyState>
    );
  }
  return (
    <>
      <ol aria-label="Findings history, newest first" className="app-tp-findings">
        {rows.map((finding) => (
          <li key={finding.id} className="app-tp-finding" data-state={finding.state}>
            <div className="app-tp-finding-main">
              <p className="app-tp-finding-head">
                <SeverityBadge severity={finding.severity} />
                <span className="app-tp-finding-message">
                  {finding.message} · {finding.citation}
                </span>
              </p>
              <p className="app-tp-finding-meta">
                <SourceTag source={finding.source} />
                <span className="font-mono">{finding.rule_id}</span>
              </p>
            </div>
            <div className="app-tp-finding-item">
              <Link
                to="/items/$itemId"
                params={{ itemId: String(finding.item_id) }}
                className="app-tp-link"
                aria-label={`${finding.item_key} v${String(finding.version_n)}: ${finding.item_title}`}
              >
                <span className="font-mono">{finding.item_key}</span> v{finding.version_n}
              </Link>
              <span className="app-tp-finding-title" title={finding.item_title}>
                {finding.item_title}
              </span>
            </div>
            <div className="app-tp-finding-state">
              <span>{FINDING_STATE_LABELS[finding.state]}</span>
              <RelativeAge at={finding.created_at} />
            </div>
          </li>
        ))}
      </ol>
      <LoadMore
        shown={`${plural(rows.length, 'finding')} shown`}
        hasMore={query.hasNextPage}
        loading={query.isFetchingNextPage}
        failed={query.isFetchNextPageError ? query.error : null}
        onLoad={() => {
          void query.fetchNextPage();
        }}
      />
    </>
  );
}

// ---- Repeat issues -------------------------------------------------------------------------------------

export function RepeatIssues({ partner }: { partner: PartnerDetailOut }): ReactNode {
  if (partner.repeat_issues.length === 0) {
    return (
      <EmptyState icon="entity.finding" title="No repeat issues">
        Rules that fire more than once across {partner.name}&apos;s items show here, dismissed findings aside.
      </EmptyState>
    );
  }
  return (
    <div className="app-tp-table-wrap">
      <table className="app-tp-table" aria-label="Repeat issues">
        <colgroup>
          <col />
          <col style={{ width: '11rem' }} />
          <col style={{ width: '6rem' }} />
          <col style={{ width: '5rem' }} />
          <col style={{ width: '7rem' }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Rule</th>
            <th scope="col">Citation</th>
            <th scope="col" className="app-tp-num">
              Findings
            </th>
            <th scope="col" className="app-tp-num">
              Items
            </th>
            <th scope="col" className="app-tp-num">
              Last seen
            </th>
          </tr>
        </thead>
        <tbody>
          {partner.repeat_issues.map((issue) => (
            <tr key={issue.rule_id}>
              <td className="font-mono app-tp-cell-title">{issue.rule_id}</td>
              <td>{issue.citation}</td>
              <td className="app-tp-num">{issue.count}</td>
              <td className="app-tp-num">{issue.items}</td>
              <td className="app-tp-num app-muted">{formatDate(issue.last_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
