/*
 * Offer terms (product-spec Screens; spec §4.3): the rates and fees approved copy may quote, per product, with
 * every published version and what it changed. A lead edits a product's terms, sees the impact preview ("14
 * approved items quote v12; 9 will need re-review"), and publishes. Mortgage prequalification has no rate
 * terms (spec §4.2 ruling 1), so it gets a sentence, not a form.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components';

import type { OfferTermsOut } from '../../api/generated/model';
import { useGetCurrentOfferTerms, useListOfferTerms } from '../../api/generated/terms/terms';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { isRetryable } from '../../ui/errorMessage';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { formatDate, PRODUCT_LABELS } from '../../ui/labels';
import { useViewer } from '../../ui/layout/Viewer';
import { SkeletonText } from '../../ui/Skeleton';
import { TermsEditor } from './TermsEditor';
import { displayRows, termsChanges } from './termsForm';
import type { TermsProduct } from './termsForm';
import { TERMS_TABS } from './termsSearch';
import type { TermsTab } from './termsSearch';

export interface TermsPageProps {
  product: TermsTab;
  onProductChange: (product: TermsTab) => void;
}

function LoadError({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <div className="app-inline-error" role="alert">
      <span>
        {what} didn&apos;t load. {apiErrorMessage(error)}
      </span>
      {isRetryable(error) && (
        <Button size="sm" onPress={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function TermsPage({ product, onProductChange }: TermsPageProps) {
  const current = useGetCurrentOfferTerms();
  const byProduct = new Map((current.data ?? []).map((terms) => [terms.product, terms]));
  // A product with unsaved edits locks the other tabs: switching would unmount (and drop) the form.
  const [dirtyTab, setDirtyTab] = useState<TermsTab | null>(null);
  const onDirty = useCallback((tab: TermsTab, dirty: boolean) => {
    setDirtyTab((prev) => (dirty ? tab : prev === tab ? null : prev));
  }, []);

  return (
    <div className="app-terms">
      <header className="app-terms-header">
        <h1 className="app-page-title">Offer terms</h1>
        <p className="app-muted">
          The rates and fees approved copy may quote. Publishing a version sends live items that quote the old
          one to Needs re-review; the rest expire.
        </p>
      </header>
      <Tabs
        selectedKey={product}
        onSelectionChange={(key) => {
          onProductChange(String(key) as TermsTab);
        }}
        disabledKeys={dirtyTab === null ? [] : TERMS_TABS.filter((tab) => tab !== dirtyTab)}
        className="app-terms-tabs"
      >
        <div className="app-terms-tabrow">
          <TabList aria-label="Products" className="app-tabs app-terms-tablist">
            {TERMS_TABS.map((tab) => {
              const terms = tab === 'mortgage_prequal' ? undefined : byProduct.get(tab);
              return (
                <Tab key={tab} id={tab} className="app-tab">
                  {PRODUCT_LABELS[tab]}
                  {terms !== undefined ? (
                    <span className="app-tab-count">v{terms.version}</span>
                  ) : (
                    tab !== 'mortgage_prequal' && (
                      // Holds the count's width in every state, so the tabs never shift.
                      <span
                        className="app-tab-count app-terms-tab-slot"
                        data-loading={current.isPending || undefined}
                        aria-hidden="true"
                      />
                    )
                  )}
                </Tab>
              );
            })}
          </TabList>
          {dirtyTab !== null && (
            <p className="app-terms-tab-lock" role="status">
              Publish or cancel your {PRODUCT_LABELS[dirtyTab].toLowerCase()} edits to switch products.
            </p>
          )}
        </div>
        {TERMS_TABS.map((tab) => (
          <TabPanel key={tab} id={tab} className="app-terms-panel">
            {tab === 'mortgage_prequal' ? (
              <EmptyState icon="entity.terms" title="Mortgage prequalification has no rate terms">
                Mortgage prequalification ads quote no standing rates or fees, so there is nothing to publish
                here; they&apos;re checked by rules only.
              </EmptyState>
            ) : current.isPending ? (
              <TermsSkeleton />
            ) : current.isError ? (
              <LoadError
                what="Offer terms"
                error={current.error}
                onRetry={() => {
                  void current.refetch();
                }}
              />
            ) : (
              <ProductTerms product={tab} current={byProduct.get(tab) ?? null} onDirty={onDirty} />
            )}
          </TabPanel>
        ))}
      </Tabs>
    </div>
  );
}

/** The read-only layout with placeholders: heading, meta line, values card | heading, history card. */
function TermsSkeleton() {
  return (
    <div role="status" aria-label="Loading offer terms" className="app-terms-body">
      <div className="app-terms-meta">
        <div className="app-terms-meta-head">
          <SkeletonText width="4.5rem" />
        </div>
        <SkeletonText width="18rem" />
        <div className="app-terms-values app-panel-skeleton">
          {Array.from({ length: 7 }, (_, i) => (
            <SkeletonText key={i} width={`${String(55 + ((i * 13) % 35))}%`} />
          ))}
        </div>
      </div>
      <div className="app-terms-history-wrap">
        <div className="app-terms-meta-head">
          <SkeletonText width="7rem" />
        </div>
        <div className="app-terms-history app-panel-skeleton app-terms-skeleton-card">
          <SkeletonText width="40%" />
          <SkeletonText width="85%" />
          <SkeletonText width="70%" />
        </div>
      </div>
    </div>
  );
}

function ProductTerms({
  product,
  current,
  onDirty,
}: {
  product: TermsProduct;
  current: OfferTermsOut | null;
  onDirty: (tab: TermsTab, dirty: boolean) => void;
}) {
  const isLead = useViewer().roles.includes('lead');
  const [editing, setEditing] = useState(false);
  const label = PRODUCT_LABELS[product];
  const reportDirty = useCallback(
    (dirty: boolean) => {
      onDirty(product, dirty);
    },
    [onDirty, product],
  );
  // Focus: opening the editor focuses its first field (autoFocus); closing it returns focus to the trigger,
  // which the editor's unmount would otherwise drop to the page body.
  const triggerId = `edit-terms-${product}`;
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!editing && restoreFocus.current) {
      restoreFocus.current = false;
      document.getElementById(triggerId)?.focus();
    }
  }, [editing, triggerId]);
  const close = () => {
    restoreFocus.current = true;
    setEditing(false);
  };

  if (current === null && !editing) {
    return (
      <EmptyState
        icon="entity.terms"
        title={`No ${label.toLowerCase()} terms published yet`}
        action={
          isLead ? (
            <Button
              id={triggerId}
              variant="primary"
              onPress={() => {
                setEditing(true);
              }}
            >
              Publish first terms
            </Button>
          ) : undefined
        }
      >
        {isLead
          ? 'Code checks compare rate claims in copy against the terms in effect, once there are some.'
          : 'A compliance lead publishes them; code checks compare rate claims in copy against them.'}
      </EmptyState>
    );
  }

  const meta = (
    <section aria-label={`${label} terms in effect`} className="app-terms-meta">
      <div className="app-terms-meta-head">
        <h2 className="app-terms-section-title">
          {editing ? `Edit ${label.toLowerCase()} terms` : 'In effect'}
        </h2>
        {isLead && !editing && (
          <Button
            id={triggerId}
            size="sm"
            icon="action.edit"
            onPress={() => {
              setEditing(true);
            }}
          >
            Edit terms
          </Button>
        )}
      </div>
      {current === null ? (
        <p className="app-muted">No terms in effect yet.</p>
      ) : (
        <p className="app-terms-meta-line">
          <span className="app-terms-version">v{current.version}</span>
          <span className="app-muted">
            since {formatDate(current.effective_from)} · published by {current.created_by_name}
            {current.note !== '' && ` · ${current.note}`}
          </span>
        </p>
      )}
      {!editing && current !== null && (
        <dl className="app-details app-terms-values">
          {displayRows(current.values).map((row) => (
            <div key={row.label} className="app-detail-row">
              <dt>{row.label}</dt>
              <dd className="app-figure" title={row.value}>
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );

  if (editing) {
    return (
      <div className="app-terms-product">
        {meta}
        <TermsEditor product={product} current={current} onClose={close} onDirtyChange={reportDirty} />
      </div>
    );
  }
  return (
    <div className="app-terms-body">
      {meta}
      <VersionHistory product={product} />
    </div>
  );
}

function VersionHistory({ product }: { product: TermsProduct }) {
  const history = useListOfferTerms({ product });
  const label = PRODUCT_LABELS[product];

  let body;
  if (history.isPending) {
    body = (
      <div role="status" aria-label="Loading version history" className="app-panel-skeleton">
        <SkeletonText width="50%" />
        <SkeletonText width="80%" />
        <SkeletonText width="65%" />
      </div>
    );
  } else if (history.isError) {
    body = (
      <LoadError
        what="Version history"
        error={history.error}
        onRetry={() => {
          void history.refetch();
        }}
      />
    );
  } else {
    const versions = [...history.data].sort((a, b) => b.version - a.version);
    body = (
      <ol aria-label={`${label} version history`} className="app-terms-history">
        {versions.map((terms, index) => {
          const previous = versions[index + 1];
          const changes = previous === undefined ? [] : termsChanges(previous.values, terms.values);
          return (
            <li key={terms.id} aria-label={`v${String(terms.version)}`} className="app-terms-history-entry">
              <p className="app-terms-history-head">
                <span className="app-terms-version">v{terms.version}</span>
                <span className="app-muted app-figure">
                  {formatDate(terms.effective_from)} –{' '}
                  {terms.effective_to === null ? 'now' : formatDate(terms.effective_to)}
                </span>
                <span className="app-muted">{terms.created_by_name}</span>
              </p>
              {previous === undefined ? (
                <p className="app-muted">
                  {terms.version === 1 ? 'First version' : 'Earliest version on record'}
                </p>
              ) : changes.length === 0 ? (
                <p className="app-muted">No value changes</p>
              ) : (
                <dl className="app-terms-changes">
                  {changes.map((change) => (
                    <div key={change.field} className="app-detail-row">
                      <dt>{change.label}</dt>
                      <dd className="app-figure">{`${change.from} → ${change.to}`}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {terms.note !== '' && <p className="app-terms-history-note">{terms.note}</p>}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <section aria-label="Version history" className="app-terms-history-wrap">
      <h2 className="app-terms-section-title">Version history</h2>
      {body}
    </section>
  );
}
