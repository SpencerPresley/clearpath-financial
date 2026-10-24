/*
 * The filters both library views share, as chips that name their choice: product, channel, partner, approved
 * dates, run dates, legacy. The approved view adds a title/key search. Everything writes to the URL.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Input,
  Popover,
  SearchField,
} from 'react-aria-components';

import { useListPartners } from '../../api/generated/partners/partners';
import { Channel, Product } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { FilterChip } from '../../ui/FilterChip';
import { TextInput } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { IconButton } from '../../ui/IconButton';
import { CHANNEL_LABELS, formatDate, PRODUCT_LABELS } from '../../ui/labels';
import { CLEARED, hasFilters } from './search';
import type { LibraryFilterPatch, LibrarySearch } from './search';

const LEGACY_OPTIONS = [
  { id: 'exclude', label: 'Excluded' },
  { id: 'only', label: 'Only' },
];

function rangeText(label: string, from: string | undefined, to: string | undefined): string {
  if (from !== undefined && to !== undefined) return `${label}: ${formatDate(from)} – ${formatDate(to)}`;
  if (from !== undefined) return `${label}: from ${formatDate(from)}`;
  if (to !== undefined) return `${label}: until ${formatDate(to)}`;
  return label;
}

function DateRangeChip({
  label,
  description,
  from,
  to,
  onChange,
}: {
  label: string;
  description: string;
  from: string | undefined;
  to: string | undefined;
  onChange: (from: string | undefined, to: string | undefined) => void;
}) {
  const active = from !== undefined || to !== undefined;
  const invalid = from !== undefined && to !== undefined && to < from;
  return (
    <span className="app-chip" data-active={active ? 'true' : undefined}>
      <DialogTrigger>
        <AriaButton className="app-chip-btn">
          <span className="truncate">{rangeText(label, from, to)}</span>
          <Icon name="action.expand" size={12} />
        </AriaButton>
        <Popover className="app-popover" placement="bottom start" offset={4}>
          <Dialog className="app-range" aria-label={label}>
            <p className="app-range-hint">{description}</p>
            <div className="app-range-fields">
              <TextInput
                type="date"
                label="From"
                value={from ?? ''}
                onChange={(value) => {
                  onChange(value === '' ? undefined : value, to);
                }}
              />
              <TextInput
                type="date"
                label="To"
                value={to ?? ''}
                errorMessage={invalid ? 'Ends before it starts' : null}
                onChange={(value) => {
                  onChange(from, value === '' ? undefined : value);
                }}
              />
            </div>
          </Dialog>
        </Popover>
      </DialogTrigger>
      {active && (
        <IconButton
          icon="action.close"
          size="sm"
          tooltip={false}
          aria-label={`Clear ${label} filter`}
          className="app-chip-clear"
          onPress={() => {
            onChange(undefined, undefined);
          }}
        />
      )}
    </span>
  );
}

function TitleSearch({
  value,
  onChange,
}: {
  value: string | undefined;
  onChange: (q: string | undefined) => void;
}) {
  const [text, setText] = useState(value ?? '');
  const emitted = useRef(value ?? '');
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  useEffect(() => {
    const incoming = value ?? '';
    if (incoming !== emitted.current) {
      emitted.current = incoming;
      setText(incoming);
    }
  }, [value]);
  useEffect(() => {
    const q = text.trim();
    if (q === emitted.current) return;
    const timer = window.setTimeout(() => {
      emitted.current = q;
      onChangeRef.current(q === '' ? undefined : q);
    }, 250);
    return () => {
      window.clearTimeout(timer);
    };
  }, [text]);
  return (
    <SearchField aria-label="Search titles" value={text} onChange={setText} className="app-queue-search">
      <Icon name="action.search" size={14} className="text-muted" />
      <Input className="app-queue-search-input" placeholder="Title or CP-1042" />
    </SearchField>
  );
}

export function LibraryFilters({
  search,
  onChange,
}: {
  search: LibrarySearch;
  onChange: (patch: LibraryFilterPatch) => void;
}) {
  const partners = useListPartners();
  const precedents = search.tab === 'precedents';
  const partnerOptions = (partners.data ?? []).map((p) => ({ id: String(p.id), label: p.name }));

  return (
    <div className="app-library-filters" role="group" aria-label="Filters">
      {search.tab === 'approved' && (
        <TitleSearch
          value={search.q}
          onChange={(q) => {
            onChange({ q });
          }}
        />
      )}
      <FilterChip
        label="Product"
        options={Object.values(Product).map((p) => ({ id: p, label: PRODUCT_LABELS[p] }))}
        selected={search.product ?? []}
        onChange={(ids) => {
          onChange({ product: ids.length > 0 ? (ids as Product[]) : undefined });
        }}
      />
      <FilterChip
        label="Channel"
        options={Object.values(Channel).map((c) => ({ id: c, label: CHANNEL_LABELS[c] }))}
        selected={search.channel ?? []}
        onChange={(ids) => {
          onChange({ channel: ids.length > 0 ? (ids as Channel[]) : undefined });
        }}
      />
      {partners.isError ? (
        <span className="app-inline-error">
          <Icon name="feedback.error" size={14} />
          Partners unavailable
        </span>
      ) : (
        <FilterChip
          label="Partner"
          options={partnerOptions}
          selected={(search.partner_id ?? []).map(String)}
          onChange={(ids) => {
            onChange({ partner_id: ids.length > 0 ? ids.map(Number) : undefined });
          }}
        />
      )}
      {/* Precedent hits are versions, but this filters on the item's latest approval: say so there. */}
      <DateRangeChip
        label={precedents ? 'Item last approved' : 'Approved'}
        description={
          precedents
            ? "The item's latest approval date, inclusive (not the matched version's)."
            : 'Approval date, inclusive.'
        }
        from={search.approved_from}
        to={search.approved_to}
        onChange={(approved_from, approved_to) => {
          onChange({ approved_from, approved_to });
        }}
      />
      {/* Placements (where approved content runs), not the planned run dates the table shows. */}
      <DateRangeChip
        label="Placement running"
        description="Has a placement running in these dates."
        from={search.run_from}
        to={search.run_to}
        onChange={(run_from, run_to) => {
          onChange({ run_from, run_to });
        }}
      />
      {/* Precedent search covers versions; legacy items have none, so the chip could only empty the list. */}
      {!precedents && (
        <FilterChip
          label="Legacy"
          mode="single"
          options={LEGACY_OPTIONS}
          selected={search.legacy === 'include' ? [] : [search.legacy]}
          onChange={(ids) => {
            const choice = ids[0];
            onChange({ legacy: choice === 'exclude' || choice === 'only' ? choice : 'include' });
          }}
        />
      )}
      {hasFilters(search) && (
        <Button
          size="sm"
          variant="ghost"
          className="app-library-clear"
          onPress={() => {
            onChange(CLEARED);
          }}
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}
