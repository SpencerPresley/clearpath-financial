/*
 * Partners (product-spec Screens): every affiliate, lead-gen site, and marketplace, with how much of their
 * content is in review and how much is approved. Status and name filters live in the URL. Partner type and
 * status are attributes, so they take no status color (spec §5.2).
 */
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { Input, Label, SearchField } from 'react-aria-components';

import { PartnerStatus } from '../../api/generated/model';
import type { PartnerRowOut } from '../../api/generated/model';
import {
  getListPartnersQueryKey,
  useCreatePartner,
  useListPartners,
} from '../../api/generated/partners/partners';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { SelectField } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { formatDate, PARTNER_STATUS_LABELS, PARTNER_TYPE_LABELS, plural } from '../../ui/labels';
import { useViewer } from '../../ui/layout/Viewer';
import { SkeletonTable } from '../../ui/Skeleton';
import { showToast } from '../../ui/toast';
import { createBody, EMPTY_PARTNER_FORM } from './partnerValues';
import { PartnerForm } from './PartnerForm';
import type { PartnersSearch } from './partnersSearch';

export interface PartnersPageProps {
  search: PartnersSearch;
  onSearchChange: (next: Partial<PartnersSearch>, options?: { replace?: boolean }) => void;
}

/** Name, type, status, items, approved, open findings, last submitted. */
const COLUMNS = ['auto', '9rem', '8rem', '6rem', '6.5rem', '8rem', '9rem'] as const;
const SKELETON_COLUMNS = COLUMNS.map((width) => (width === 'auto' ? '1fr' : width));

type StatusChoice = PartnerStatus | 'all';
const STATUS_OPTIONS: { id: StatusChoice; label: string }[] = [
  { id: 'all', label: 'All statuses' },
  ...Object.values(PartnerStatus).map((id) => ({ id, label: PARTNER_STATUS_LABELS[id] })),
];

const SEARCH_DEBOUNCE_MS = 250;
const NEW_HEADER_ID = 'new-partner';
const NEW_EMPTY_ID = 'new-partner-empty';

export function PartnersPage({ search, onSearchChange }: PartnersPageProps) {
  const isLead = useViewer().roles.includes('lead');
  const [creating, setCreating] = useState(false);
  // Cancel returns focus to whichever New partner button opened the form (the form's unmount drops it).
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!creating && restoreFocus.current) {
      restoreFocus.current = false;
      (document.getElementById(NEW_HEADER_ID) ?? document.getElementById(NEW_EMPTY_ID))?.focus();
    }
  }, [creating]);
  const [query, setQuery] = useState(search.q ?? '');
  const list = useListPartners(
    { status: search.status, q: search.q },
    // Keep the rows while a filter change loads (marked busy) instead of flashing the skeleton.
    { query: { placeholderData: keepPreviousData } },
  );

  // The search box writes the URL after a pause; the URL (back/forward, links) wins when it changes to
  // something the box doesn't already say (so a trailing space mid-word survives the round trip).
  const [urlQ, setUrlQ] = useState(search.q);
  if (search.q !== urlQ) {
    setUrlQ(search.q);
    if ((query.trim() === '' ? undefined : query.trim()) !== search.q) setQuery(search.q ?? '');
  }
  useEffect(() => {
    const next = query.trim() === '' ? undefined : query.trim();
    if (next === search.q) return;
    const timer = window.setTimeout(() => {
      onSearchChange({ q: next }, { replace: true });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [query, search.q, onSearchChange]);

  const filtered = search.status !== undefined || search.q !== undefined;
  const rows = list.data ?? [];

  let body;
  if (list.isPending) {
    body = <SkeletonTable rows={6} columns={SKELETON_COLUMNS} label="Loading partners" />;
  } else if (list.isError) {
    body = (
      <div className="app-inline-error" role="alert">
        <span>Partners didn&apos;t load. {apiErrorMessage(list.error)}</span>
        <Button
          size="sm"
          onPress={() => {
            void list.refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  } else if (rows.length === 0 && filtered) {
    body = (
      <EmptyState
        icon="entity.partner"
        title="No partners match these filters"
        action={
          <Button
            size="sm"
            onPress={() => {
              setQuery('');
              onSearchChange({ status: undefined, q: undefined });
            }}
          >
            Clear filters
          </Button>
        }
      >
        Try another name or status.
      </EmptyState>
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        icon="entity.partner"
        title="No partners yet"
        action={
          isLead && !creating ? (
            <Button
              id={NEW_EMPTY_ID}
              variant="primary"
              size="sm"
              onPress={() => {
                setCreating(true);
              }}
            >
              New partner
            </Button>
          ) : undefined
        }
      >
        Affiliates, lead-gen sites, and marketplaces that publish ClearPath offers. Add one to attach its
        agreement and track its items.
      </EmptyState>
    );
  } else {
    body = <PartnersTable rows={rows} busy={list.isFetching && list.isPlaceholderData} />;
  }

  return (
    <div className="app-partners">
      <header className="app-partners-header">
        <div>
          <h1 className="app-page-title">Partners</h1>
          <p className="app-muted">{list.isSuccess ? plural(rows.length, 'partner') : '\u00a0'}</p>
        </div>
        {isLead && !creating && !(list.isSuccess && rows.length === 0 && !filtered) && (
          <Button
            id={NEW_HEADER_ID}
            variant="primary"
            onPress={() => {
              setCreating(true);
            }}
          >
            New partner
          </Button>
        )}
      </header>
      {creating && (
        <CreatePartner
          onCancel={() => {
            restoreFocus.current = true;
            setCreating(false);
          }}
          onCreated={() => {
            setCreating(false);
          }}
        />
      )}
      <div className="app-partners-filters" role="search">
        <SearchField value={query} onChange={setQuery} className="app-partners-search">
          <Label className="sr-only">Search partners</Label>
          <Icon name="action.search" size={14} className="app-partners-search-icon" />
          <Input className="app-input" placeholder="Search by name" />
        </SearchField>
        <SelectField<StatusChoice>
          label="Status"
          hideLabel
          size="sm"
          value={search.status ?? 'all'}
          onChange={(value) => {
            onSearchChange({ status: value === null || value === 'all' ? undefined : value });
          }}
          options={STATUS_OPTIONS}
          className="app-partners-status"
        />
      </div>
      {body}
    </div>
  );
}

function PartnersTable({ rows, busy }: { rows: readonly PartnerRowOut[]; busy: boolean }) {
  return (
    <div className="app-tp-table-wrap" aria-busy={busy || undefined}>
      <table className="app-tp-table" aria-label="Partners">
        <colgroup>
          {COLUMNS.map((width, index) => (
            <col key={index} style={width === 'auto' ? undefined : { width }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col" className="app-tp-num">
              Items
            </th>
            <th scope="col" className="app-tp-num">
              Approved
            </th>
            <th scope="col" className="app-tp-num">
              Open findings
            </th>
            <th scope="col" className="app-tp-num">
              Last submitted
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="app-tp-cell-title">
                <Link
                  to="/partners/$partnerId"
                  params={{ partnerId: String(row.id) }}
                  className="app-tp-link"
                >
                  {row.name}
                </Link>
              </td>
              <td>{PARTNER_TYPE_LABELS[row.type]}</td>
              <td>
                <span className="app-badge app-badge-outline">{PARTNER_STATUS_LABELS[row.status]}</span>
              </td>
              <td className="app-tp-num">{row.item_count}</td>
              <td className="app-tp-num">{row.approved_count}</td>
              <td className="app-tp-num">{row.open_findings_count}</td>
              <td className="app-tp-num app-muted">
                {/* Null only when the partner has no items (every item has a submitted date). */}
                {row.last_submitted_at === null ? '—' : formatDate(row.last_submitted_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreatePartner({ onCancel, onCreated }: { onCancel: () => void; onCreated: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const create = useCreatePartner();
  return (
    <section className="app-partners-create">
      <h2 className="app-tp-section-title">New partner</h2>
      <PartnerForm
        label="New partner"
        initial={EMPTY_PARTNER_FORM}
        submitLabel="Add partner"
        pending={create.isPending}
        onCancel={onCancel}
        onSubmit={(values, report) => {
          create.mutate(
            { data: createBody(values) },
            {
              onSuccess: (partner) => {
                showToast({ title: `Added ${partner.name}`, description: 'Attach the agreement next.' });
                void queryClient.invalidateQueries({ queryKey: getListPartnersQueryKey() });
                onCreated();
                void navigate({ to: '/partners/$partnerId', params: { partnerId: String(partner.id) } });
              },
              onError: report,
            },
          );
        }}
      />
    </section>
  );
}
