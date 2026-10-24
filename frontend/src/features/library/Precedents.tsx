/*
 * Precedent search: every version that ever received an approval, one hit per item (its latest matching
 * version). Each hit shows the matched wording highlighted, the version it came from with that version's own
 * decision, and the item's status now (ledger ruling: precedent value doesn't lapse; run-permission does).
 */
import { keepPreviousData } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import type { Key } from 'react-aria-components';
import { Input, SearchField, ToggleButton, ToggleButtonGroup } from 'react-aria-components';

import { useSearchLibrary } from '../../api/generated/library/library';
import type { SearchHitOut } from '../../api/generated/model';
import { OutcomeBadge, StatusBadge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
import { ItemKey } from '../../ui/ItemKey';
import { SkeletonBadge, SkeletonText } from '../../ui/Skeleton';
import { SnippetText } from '../../ui/SnippetText';
import { CHANNEL_LABELS, formatDate, plural, PRODUCT_LABELS } from '../../ui/labels';
import { EvidencePackAction } from './EvidencePackAction';
import { hasFilters, SEARCH_LIMIT, toSearchParams } from './search';
import type { LibrarySearch, SearchModeId } from './search';

export const MODE_HINT: Record<SearchModeId, string> = {
  phrase: 'Phrase: this exact wording, in any letter case.',
  text: 'Text: the words in any order and form. Use "quotes" for a phrase, -word to exclude, or for either.',
};

function QueryField({
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
    if (text === emitted.current) return;
    const timer = window.setTimeout(() => {
      emitted.current = text;
      onChangeRef.current(text.trim() === '' ? undefined : text);
    }, 300);
    return () => {
      window.clearTimeout(timer);
    };
  }, [text]);
  return (
    <SearchField
      aria-label="Search approved copy"
      value={text}
      onChange={setText}
      className="app-precedent-search"
    >
      <Icon name="action.search" size={16} className="text-muted" />
      <Input
        className="app-precedent-search-input"
        placeholder="Wording to find, e.g. won't affect your credit score"
      />
    </SearchField>
  );
}

export function PrecedentSearchBar({
  search,
  onQuery,
  onMode,
}: {
  search: LibrarySearch;
  onQuery: (query: string | undefined) => void;
  onMode: (mode: SearchModeId) => void;
}) {
  return (
    <div className="app-precedent-bar">
      <QueryField value={search.query} onChange={onQuery} />
      <ToggleButtonGroup
        aria-label="Search mode"
        selectionMode="single"
        disallowEmptySelection
        selectedKeys={new Set<Key>([search.mode])}
        onSelectionChange={(keys) => {
          const next = [...keys][0];
          if (next === 'phrase' || next === 'text') onMode(next);
        }}
        className="app-segmented"
      >
        <ToggleButton id="phrase" className="app-segmented-item">
          Phrase
        </ToggleButton>
        <ToggleButton id="text" className="app-segmented-item">
          Text
        </ToggleButton>
      </ToggleButtonGroup>
      <p className="app-precedent-hint">{MODE_HINT[search.mode]}</p>
    </div>
  );
}

function Hit({ hit }: { hit: SearchHitOut }) {
  const meta = [PRODUCT_LABELS[hit.product], CHANNEL_LABELS[hit.channel], hit.partner_name].filter(
    (part): part is string => part !== null,
  );
  return (
    <li className="app-precedent">
      <div className="app-precedent-head">
        <ItemKey value={hit.key} copyable={false} />
        <Link
          to="/items/$itemId"
          params={{ itemId: String(hit.item_id) }}
          className="app-library-link app-precedent-title"
        >
          {hit.title}
        </Link>
        <span className="app-precedent-now">
          <span className="app-precedent-label">Now</span>
          <StatusBadge status={hit.status} />
        </span>
      </div>
      <p className="app-precedent-snippet">
        <SnippetText parts={hit.snippet} />
      </p>
      <div className="app-precedent-meta">
        <span className="app-precedent-version">
          <span>Matched v{hit.version_n}</span>
          {hit.version_outcome !== null && <OutcomeBadge outcome={hit.version_outcome} />}
          {hit.version_decided_at !== null && (
            <span className="app-figure text-muted">{formatDate(hit.version_decided_at)}</span>
          )}
        </span>
        <span className="app-precedent-facts">{meta.join(' · ')}</span>
        <span className="app-precedent-action">
          <EvidencePackAction itemId={hit.item_id} itemKey={hit.key} isLegacy={false} />
        </span>
      </div>
    </li>
  );
}

function HitsSkeleton() {
  return (
    <div role="status" aria-label="Searching precedents" aria-busy="true">
      <ul className="app-precedents" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <li key={i} className="app-precedent">
            <div className="app-precedent-head">
              <SkeletonText width="4rem" />
              <SkeletonText width={`${String(14 + ((i * 7) % 10))}rem`} />
              <span className="app-precedent-now">
                <SkeletonBadge />
              </span>
            </div>
            <p className="app-precedent-snippet">
              <SkeletonText width={`${String(60 + ((i * 13) % 30))}%`} />
            </p>
            <div className="app-precedent-meta">
              <SkeletonText width="12rem" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PrecedentResults({
  search,
  onMode,
  onClear,
}: {
  search: LibrarySearch;
  onMode: (mode: SearchModeId) => void;
  onClear: () => void;
}) {
  const params = toSearchParams(search);
  const enabled = params.query !== '';
  const results = useSearchLibrary(params, { query: { enabled, placeholderData: keepPreviousData } });

  if (!enabled) {
    return (
      <div className="app-library-region">
        <EmptyState icon="action.search" title="Search past approvals">
          Finds approved wording in every version that was ever approved, including items that have since
          expired or gone back for re-review.
        </EmptyState>
      </div>
    );
  }
  if (results.isPending) {
    return (
      <div className="app-library-region">
        <HitsSkeleton />
      </div>
    );
  }
  if (results.isError && results.data === undefined) {
    return (
      <div className="app-library-region" role="alert">
        <EmptyState
          icon="feedback.error"
          title="Couldn't search precedents"
          action={
            <Button
              size="sm"
              icon="action.reload"
              onPress={() => {
                void results.refetch();
              }}
            >
              Retry
            </Button>
          }
        >
          {errorMessage(results.error, 'Check your connection and try again.')}
        </EmptyState>
      </div>
    );
  }
  const hits = results.data.hits;
  if (hits.length === 0) {
    const other: SearchModeId = search.mode === 'phrase' ? 'text' : 'phrase';
    return (
      <div className="app-library-region">
        <EmptyState
          icon="action.search"
          title={`No precedents for “${params.query}”`}
          action={
            <>
              <Button
                size="sm"
                onPress={() => {
                  onMode(other);
                }}
              >
                {other === 'text' ? 'Try text mode' : 'Try phrase mode'}
              </Button>
              {hasFilters(search) && (
                <Button size="sm" variant="ghost" onPress={onClear}>
                  Clear filters
                </Button>
              )}
            </>
          }
        >
          {search.mode === 'phrase'
            ? 'No approved version contains this exact wording. Text mode also matches other word forms and orders.'
            : 'No approved version matches these words.'}
        </EmptyState>
      </div>
    );
  }
  return (
    <div className="app-library-region" aria-busy={results.isPlaceholderData ? 'true' : undefined}>
      <ol className="app-precedents" aria-label="Precedents">
        {hits.map((hit) => (
          <Hit key={hit.item_id} hit={hit} />
        ))}
      </ol>
      <div className="app-table-footer">
        <span className="app-figure">
          {hits.length >= SEARCH_LIMIT
            ? `Top ${String(SEARCH_LIMIT)} precedents · narrow the search or filters for the rest`
            : plural(hits.length, 'precedent')}
        </span>
      </div>
    </div>
  );
}
