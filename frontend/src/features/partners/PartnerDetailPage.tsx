/*
 * One partner (product-spec Screens: "agreement and evidence, items, findings history, and repeat issues").
 * The side column holds what a reviewer checks affiliate copy against: the partner's facts and its signed
 * agreement and evidence. Leads edit the facts and upload; everyone else reads.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { useRef, useState } from 'react';
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components';

import type { AttachmentKind, PartnerDetailOut } from '../../api/generated/model';
import {
  getGetPartnerQueryKey,
  getListPartnersQueryKey,
  useGetPartner,
  uploadPartnerAttachment,
  useUpdatePartner,
} from '../../api/generated/partners/partners';
import { ApiError } from '../../api/mutator';
import { Button } from '../../ui/Button';
import { ButtonLink } from '../../ui/ButtonLink';
import { EmptyState } from '../../ui/EmptyState';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { SelectField } from '../../ui/forms/fields';
import {
  ATTACHMENT_KIND_LABELS,
  formatBytes,
  formatDate,
  PARTNER_STATUS_LABELS,
  PARTNER_TYPE_LABELS,
} from '../../ui/labels';
import { useViewer } from '../../ui/layout/Viewer';
import { RelativeAge } from '../../ui/RelativeAge';
import { SkeletonTable, SkeletonText } from '../../ui/Skeleton';
import { showToast } from '../../ui/toast';
import { partnerFormFrom, patchBody, websiteHref, websiteLabel } from './partnerValues';
import { PartnerForm } from './PartnerForm';
import type { PartnerTab } from './partnersSearch';
import { FindingsHistory, PartnerItems, RepeatIssues } from './PartnerTabs';

export interface PartnerDetailPageProps {
  partnerId: number;
  tab: PartnerTab;
  onTabChange: (tab: PartnerTab) => void;
}

export function PartnerDetailPage({ partnerId, tab, onTabChange }: PartnerDetailPageProps) {
  const partner = useGetPartner(partnerId);

  if (partner.isPending) return <DetailSkeleton />;
  if (partner.isError) {
    if (partner.error instanceof ApiError && partner.error.status === 404) {
      return (
        <div className="app-partner">
          <EmptyState
            icon="entity.partner"
            title={`Partner ${String(partnerId)} doesn't exist`}
            action={
              <ButtonLink to="/partners" size="sm">
                All partners
              </ButtonLink>
            }
          >
            It may have been a mistyped link.
          </EmptyState>
        </div>
      );
    }
    return (
      <div className="app-partner">
        <div className="app-inline-error" role="alert">
          <span>This partner didn&apos;t load. {apiErrorMessage(partner.error)}</span>
          <Button
            size="sm"
            onPress={() => {
              void partner.refetch();
            }}
          >
            Retry
          </Button>
        </div>
      </div>
    );
  }
  const detail = partner.data;

  return (
    <div className="app-partner">
      <header className="app-partner-header">
        <nav aria-label="Breadcrumb" className="app-partner-crumbs">
          <Link to="/partners" className="app-tp-link">
            Partners
          </Link>
        </nav>
        <div className="app-partner-title-row">
          <h1 className="app-page-title">{detail.name}</h1>
          <span className="app-muted">{PARTNER_TYPE_LABELS[detail.type]}</span>
          <span className="app-badge app-badge-outline">{PARTNER_STATUS_LABELS[detail.status]}</span>
        </div>
        <div className="app-partner-stats">
          <Stat value={detail.item_count} label="Items" />
          <Stat value={detail.approved_count} label="Approved" />
          <Stat value={detail.open_findings_count} label="Open findings" />
          <div role="group" aria-label="Last submitted" className="app-partner-stat">
            <span className="app-partner-stat-figure">
              {detail.last_submitted_at === null ? '—' : <RelativeAge at={detail.last_submitted_at} />}
            </span>
            <span className="app-partner-stat-label">Last submitted</span>
          </div>
        </div>
      </header>

      <div className="app-partner-body">
        <Tabs
          selectedKey={tab}
          onSelectionChange={(key) => {
            onTabChange(String(key) as PartnerTab);
          }}
          className="app-partner-main"
        >
          <TabList aria-label="Partner records" className="app-tabs">
            <Tab id="items" className="app-tab">
              Items <span className="app-tab-count">{detail.item_count}</span>
            </Tab>
            <Tab id="findings" className="app-tab">
              Findings history
            </Tab>
            <Tab id="repeat" className="app-tab">
              Repeat issues <span className="app-tab-count">{detail.repeat_issues.length}</span>
            </Tab>
          </TabList>
          <TabPanel id="items" className="app-partner-panel">
            <PartnerItems partner={detail} />
          </TabPanel>
          <TabPanel id="findings" className="app-partner-panel">
            <FindingsHistory partner={detail} />
          </TabPanel>
          <TabPanel id="repeat" className="app-partner-panel">
            <RepeatIssues partner={detail} />
          </TabPanel>
        </Tabs>
        <aside className="app-partner-side">
          <PartnerFacts partner={detail} />
          <PartnerAttachments partner={detail} />
        </aside>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div role="group" aria-label={`${String(value)} ${label}`} className="app-partner-stat">
      <span className="app-partner-stat-figure">{value}</span>
      <span className="app-partner-stat-label">{label}</span>
    </div>
  );
}

/** Header, tabs over a table, and the two side boxes, in their final places. */
function DetailSkeleton() {
  return (
    <div className="app-partner" role="status" aria-label="Loading partner">
      <div className="app-partner-header">
        <SkeletonText width="4rem" />
        <div className="app-partner-title-row">
          <SkeletonText width="12rem" />
        </div>
        <div className="app-partner-stats">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="app-partner-stat">
              <span className="app-partner-stat-figure">
                <SkeletonText width="2rem" />
              </span>
              <SkeletonText width="5rem" />
            </div>
          ))}
        </div>
      </div>
      <div className="app-partner-body">
        <div className="app-partner-main">
          <div className="app-tabs app-partner-skeleton-tabs">
            <SkeletonText width="16rem" />
          </div>
          <SkeletonTable rows={4} columns={['6.5rem', '1fr', '9rem', '5rem', '7rem']} label="Loading items" />
        </div>
        <div className="app-partner-side">
          {[5, 4].map((lines, box) => (
            <div key={box} className="app-partner-section app-panel-skeleton">
              {Array.from({ length: lines }, (_, i) => (
                <SkeletonText key={i} width={`${String(50 + ((i * 19 + box * 7) % 45))}%`} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- Facts -------------------------------------------------------------------------------------------

function PartnerFacts({ partner }: { partner: PartnerDetailOut }) {
  const isLead = useViewer().roles.includes('lead');
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const update = useUpdatePartner();

  return (
    <section aria-label="Details" className="app-partner-section">
      <div className="app-partner-section-head">
        <h2 className="app-tp-section-title">Details</h2>
        {isLead && !editing && (
          <Button
            size="sm"
            variant="ghost"
            icon="action.edit"
            onPress={() => {
              setEditing(true);
            }}
          >
            Edit details
          </Button>
        )}
      </div>
      {editing ? (
        <PartnerForm
          label="Edit partner details"
          layout="stacked"
          withStatus
          initial={partnerFormFrom(partner)}
          submitLabel="Save"
          pending={update.isPending}
          onCancel={() => {
            setEditing(false);
          }}
          onSubmit={(values, report) => {
            const data = patchBody(values, partner);
            if (Object.keys(data).length === 0) {
              setEditing(false);
              return;
            }
            update.mutate(
              { partnerId: partner.id, data },
              {
                onSuccess: (updated) => {
                  queryClient.setQueryData(getGetPartnerQueryKey(partner.id), updated);
                  void queryClient.invalidateQueries({ queryKey: getListPartnersQueryKey() });
                  setEditing(false);
                },
                onError: report,
              },
            );
          }}
        />
      ) : (
        <dl className="app-details app-partner-facts">
          <div className="app-detail-row">
            <dt>Website</dt>
            <dd>
              {partner.website === '' ? (
                <span className="app-muted">Not recorded</span>
              ) : (
                <a href={websiteHref(partner.website)} className="app-link" target="_blank" rel="noreferrer">
                  {websiteLabel(partner.website)}
                </a>
              )}
            </dd>
          </div>
          <div className="app-detail-row">
            <dt>Contact</dt>
            <dd>
              {partner.contact_email === '' ? (
                <span className="app-muted">Not recorded</span>
              ) : (
                <a href={`mailto:${partner.contact_email}`} className="app-link">
                  {partner.contact_email}
                </a>
              )}
            </dd>
          </div>
          <div className="app-detail-row">
            <dt>Agreement signed</dt>
            <dd>
              {partner.agreement_signed_on === null ? (
                <span className="app-muted">Not recorded</span>
              ) : (
                formatDate(partner.agreement_signed_on)
              )}
            </dd>
          </div>
          <div className="app-detail-row">
            <dt>Added</dt>
            <dd>{formatDate(partner.created_at)}</dd>
          </div>
          {partner.notes !== '' && (
            <div className="app-detail-row">
              <dt>Notes</dt>
              <dd className="app-partner-notes">{partner.notes}</dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
}

// ---- Agreement and evidence -----------------------------------------------------------------------

// Agreements first: the partner screen is where they live (the item Evidence tab leaves them out).
const KIND_ORDER: AttachmentKind[] = [
  'agreement',
  'screenshot',
  'substantiation',
  'rate_sheet',
  'creative',
  'consent_record',
  'prescreen_criteria',
  'other',
];

function PartnerAttachments({ partner }: { partner: PartnerDetailOut }) {
  const isLead = useViewer().roles.includes('lead');
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<AttachmentKind | null>('agreement');
  const [error, setError] = useState<string | null>(null);
  // The generated fetcher, called directly (not through its hook) so tests can stand in for the multipart
  // request, which jsdom's File can't make.
  const upload = useMutation({
    mutationFn: ({ file, kind: k }: { file: File; kind: AttachmentKind }) =>
      uploadPartnerAttachment(partner.id, { file, kind: k }),
    onSuccess: (attachment) => {
      setError(null);
      if (fileInput.current !== null) fileInput.current.value = '';
      showToast({ title: `Uploaded ${attachment.original_name}` });
      void queryClient.invalidateQueries({ queryKey: getGetPartnerQueryKey(partner.id) });
    },
    onError: (e) => {
      setError(apiErrorMessage(e));
    },
  });

  return (
    <section aria-label="Agreement and evidence" className="app-partner-section">
      <h2 className="app-tp-section-title">Agreement and evidence</h2>
      {partner.attachments.length === 0 ? (
        <p className="app-muted">
          No agreement on file.{' '}
          {isLead ? 'Upload the signed agreement so reviewers can check copy against it.' : ''}
        </p>
      ) : (
        <ul className="app-evidence-list">
          {partner.attachments.map((a) => (
            <li key={a.id} aria-label={a.original_name} className="app-evidence">
              <a href={a.download_url} className="app-link app-partner-file">
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
      {isLead && (
        <form
          className="app-panel-form"
          aria-label="Upload an attachment"
          onSubmit={(event) => {
            event.preventDefault();
            const file = fileInput.current?.files?.[0];
            if (file === undefined || kind === null) {
              setError('Choose a file and its kind.');
              return;
            }
            upload.mutate({ kind, file });
          }}
        >
          <SelectField
            label="Kind"
            size="sm"
            value={kind}
            onChange={setKind}
            options={KIND_ORDER.map((k) => ({ id: k, label: ATTACHMENT_KIND_LABELS[k] }))}
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
              {upload.isPending ? 'Uploading…' : 'Upload'}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
