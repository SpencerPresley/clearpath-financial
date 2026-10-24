/*
 * Offer terms (product-spec Screens; spec §4.3): the rates and fees approved copy may quote, per product, with
 * every published version and what it changed. A lead edits a product's terms, sees the impact preview ("14
 * approved items quote v12; 9 will need re-review"), and publishes. Mortgage prequalification has no rate
 * terms (spec §4.2 ruling 1), so it gets a sentence, not a form.
 */
import { useState } from 'react';
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components';

import type { OfferTermsOut } from '../../api/generated/model';
import { useGetCurrentOfferTerms, useListOfferTerms } from '../../api/generated/terms/terms';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
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
      <Button size="sm" onPress={onRetry}>
        Retry
      </Button>
    </div>
  );
}

export function TermsPage({ product, onProductChange }: TermsPageProps) {
  const current = useGetCurrentOfferTerms();
  const byProduct = new Map((current.data ?? []).map((terms) => [terms.product, terms]));

  return (
    <div className="app-terms">
      <header className="app-terms-header">
        <h1 className="app-page-title">Offer terms</h1>
        <p className="app-muted">
          The rates and fees approved copy may quote. Publishing a version sends items that quote the old one
          back for re-review.
        </p>
      </header>
      <Tabs
        selectedKey={product}
        onSelectionChange={(key) => {
          onProductChange(String(key) as TermsTab);
        }}
        className="app-terms-tabs"
      >
        <TabList aria-label="Products" className="app-tabs app-terms-tablist">
          {TERMS_TABS.map((tab) => {
            const terms = tab === 'mortgage_prequal' ? undefined : byProduct.get(tab);
            return (
              <Tab key={tab} id={tab} className="app-tab">
                {PRODUCT_LABELS[tab]}
                {terms !== undefined && <span className="app-tab-count">v{terms.version}</span>}
              </Tab>
            );
          })}
        </TabList>
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
              <ProductTerms product={tab} current={byProduct.get(tab) ?? null} />
            )}
          </TabPanel>
        ))}
      </Tabs>
    </div>
  );
}

function TermsSkeleton() {
  return (
    <div role="status" aria-label="Loading offer terms" className="app-terms-body">
      <div className="app-terms-values app-panel-skeleton">
        {Array.from({ length: 7 }, (_, i) => (
          <SkeletonText key={i} width={`${String(60 + ((i * 13) % 35))}%`} />
        ))}
      </div>
      <div className="app-panel-skeleton">
        <SkeletonText width="40%" />
        <SkeletonText width="85%" />
        <SkeletonText width="70%" />
      </div>
    </div>
  );
}

function ProductTerms({ product, current }: { product: TermsProduct; current: OfferTermsOut | null }) {
  const isLead = useViewer().roles.includes('lead');
  const [editing, setEditing] = useState(false);
  const label = PRODUCT_LABELS[product];

  if (current === null && !editing) {
    return (
      <EmptyState
        icon="entity.terms"
        title={`No ${label.toLowerCase()} terms published yet`}
        action={
          isLead ? (
            <Button
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
      <div className="app-terms-meta-line">
        {current === null ? (
          <span>No terms in effect</span>
        ) : (
          <>
            <span className="app-terms-version">v{current.version}</span>
            <span className="app-muted">
              In effect since {formatDate(current.effective_from)} · published by {current.created_by_name}
            </span>
          </>
        )}
        {isLead && !editing && (
          <Button
            size="sm"
            icon="action.edit"
            className="app-terms-edit-btn"
            onPress={() => {
              setEditing(true);
            }}
          >
            Edit terms
          </Button>
        )}
      </div>
      {current !== null && current.note !== '' && <p className="app-terms-meta-note">{current.note}</p>}
      {!editing && current !== null && (
        <dl className="app-details app-terms-values">
          {displayRows(current.values).map((row) => (
            <div key={row.label} className="app-detail-row">
              <dt>{row.label}</dt>
              <dd className="app-figure">{row.value}</dd>
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
        <TermsEditor
          product={product}
          current={current}
          onClose={() => {
            setEditing(false);
          }}
        />
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
