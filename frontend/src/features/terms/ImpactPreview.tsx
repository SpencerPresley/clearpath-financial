/*
 * What publishing would do (F's ImpactPreviewOut): the summary sentence as the server wrote it, the outcomes
 * (live items to Needs re-review, the rest expire; items already in re-review get new numbers), how many
 * re-reviews need a full review, the quoted fields that change, the partners, and every affected item.
 * "Needs re-review" carries the alert tone because it is that status (spec §5.2); live/not live, lane, and partner
 * are facts, uncolored.
 *
 * Links open a new tab: the lead is mid-edit, and leaving the page would drop the form.
 */
import { Link } from '@tanstack/react-router';

import type { ImpactPreviewOut } from '../../api/generated/model';
import { StatusBadge, StatusMark } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { ItemKey } from '../../ui/ItemKey';
import { plural } from '../../ui/labels';
import { SkeletonText } from '../../ui/Skeleton';
import { TERMS_FIELD_LABELS } from './termsForm';

export const AFFECTED_ITEMS_ID = 'terms-affected-items';

/**
 * Of the approved live items going to Needs re-review, those whose quoted numbers no longer fit the copy: no
 * fast-track, a full review. (The API's `normal_lane` also counts expired and already-in-re-review items, so it
 * isn't a subset of `will_need_rereview`.)
 */
export function fullReviewCount(preview: ImpactPreviewOut): number {
  return preview.items.filter(
    (i) => i.item.status === 'approved' && i.will_become === 'needs_rereview' && i.lane === 'normal',
  ).length;
}

/** Items already in re-review that get a generated version with the new numbers (fast-track lane only). */
export function refreshedCount(preview: ImpactPreviewOut): number {
  return preview.items.filter((i) => i.item.status === 'needs_rereview' && i.lane === 'fast_track').length;
}

/** "9 live items move to Needs re-review; 5 expire." The counts, not a blanket "move to re-review". */
export function outcomeSentence(preview: ImpactPreviewOut): string {
  const parts: string[] = [];
  if (preview.will_need_rereview > 0) {
    const n = preview.will_need_rereview;
    parts.push(`${plural(n, 'live item')} ${n === 1 ? 'moves' : 'move'} to Needs re-review`);
  }
  if (preview.will_expire > 0) {
    parts.push(`${String(preview.will_expire)} ${preview.will_expire === 1 ? 'expires' : 'expire'}`);
  }
  const refreshed = refreshedCount(preview);
  if (refreshed > 0) {
    parts.push(
      `${String(refreshed)} already in re-review ${refreshed === 1 ? 'gets' : 'get'} the new numbers`,
    );
  }
  return parts.length === 0 ? 'No items change status.' : `${parts.join('; ')}.`;
}

function Count({
  value,
  label,
  mark,
  detail,
}: {
  value: number;
  label: string;
  mark?: 'needs_rereview' | 'expired';
  detail?: string;
}) {
  return (
    <div
      role="group"
      aria-label={`${String(value)} ${label}${detail === undefined ? '' : `, ${detail}`}`}
      className="app-terms-count"
    >
      <span className="app-terms-count-figure" aria-hidden="true">
        {value}
        {mark !== undefined && <StatusMark status={mark} />}
      </span>
      <span className="app-terms-count-label" aria-hidden="true">
        {label}
      </span>
      {detail !== undefined && (
        <span className="app-terms-count-detail" aria-hidden="true">
          {detail}
        </span>
      )}
    </div>
  );
}

/** Placeholder in the loaded panel's shape: summary line, the counts row, one more line. */
function ImpactSkeleton() {
  // Each bar sits in the loaded element's own type, so every line keeps its height and nothing moves when the
  // preview lands: summary, the counts row, two lines, then partners.
  return (
    <div role="status" aria-label="Checking the impact" className="app-terms-impact-body">
      <p className="app-terms-summary app-tp-skel-line">
        <SkeletonText width="85%" />
      </p>
      <div className="app-terms-counts">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="app-terms-count">
            <span className="app-terms-count-figure app-tp-skel-line">
              <SkeletonText width="1.5rem" />
            </span>
            <span className="app-terms-count-label app-tp-skel-line">
              <SkeletonText width="6rem" />
            </span>
            <span className="app-terms-count-detail app-tp-skel-line">
              <SkeletonText width="4rem" />
            </span>
          </div>
        ))}
      </div>
      <p className="app-terms-impact-line app-tp-skel-line">
        <SkeletonText width="45%" />
      </p>
      <p className="app-terms-impact-line app-tp-skel-line">
        <SkeletonText width="25%" />
      </p>
      <div>
        <p className="app-panel-heading app-tp-skel-line">
          <SkeletonText width="4rem" />
        </p>
        <ul className="app-terms-partners">
          {[0, 1].map((i) => (
            <li key={i}>
              <SkeletonText width={i === 0 ? '6rem' : '5rem'} />
              <SkeletonText width="3rem" />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function ImpactPanel({
  nextVersion,
  preview,
  stale,
  loading,
  error,
  onRetry,
}: {
  nextVersion: number;
  preview: ImpactPreviewOut | undefined;
  /** The preview on screen is for earlier values; the next one is loading or a field is mid-edit. */
  stale: boolean;
  loading: boolean;
  /** The preview for the current values failed. */
  error: unknown;
  onRetry: () => void;
}) {
  const fullReview = preview === undefined ? 0 : fullReviewCount(preview);
  return (
    <section
      aria-label={`Impact of publishing v${String(nextVersion)}`}
      aria-busy={stale && preview !== undefined ? true : undefined}
      className="app-terms-impact"
    >
      <h2 className="app-terms-section-title">Impact</h2>
      {error !== null ? (
        <div className="app-inline-error" role="alert">
          <span>Couldn&apos;t preview the impact. {apiErrorMessage(error)}</span>
          <Button size="sm" onPress={onRetry}>
            Retry
          </Button>
        </div>
      ) : loading ? (
        <ImpactSkeleton />
      ) : preview === undefined ? (
        <p className="app-muted">
          Change a value to see which approved items and partners quote these terms before you publish.
        </p>
      ) : (
        <div className="app-terms-impact-body">
          <p className="app-terms-summary">{preview.summary}</p>
          <div className="app-terms-counts">
            <Count
              value={preview.will_need_rereview}
              label="Needs re-review"
              mark="needs_rereview"
              detail={
                preview.will_need_rereview === 0
                  ? 'live items'
                  : fullReview === 0
                    ? 'all fast-track'
                    : `of ${String(preview.will_need_rereview)}: ${String(fullReview)} full review`
              }
            />
            <Count value={preview.will_expire} label="Expire" mark="expired" detail="not live" />
            <Count
              value={preview.already_in_rereview}
              label="In re-review now"
              detail={
                preview.already_in_rereview === 0
                  ? 'none'
                  : `${String(refreshedCount(preview))} get new numbers`
              }
            />
          </div>
          {preview.changed_fields.length > 0 && (
            <p className="app-terms-impact-line">
              <span className="app-muted">Quoted fields that change: </span>
              {preview.changed_fields.map((field) => TERMS_FIELD_LABELS[field]).join(', ')}
            </p>
          )}
          {preview.items.length > 0 && (
            <p className="app-terms-impact-line">
              {/* A button, not a #hash link: the router would take the hash into the URL. */}
              <button
                type="button"
                className="app-link app-terms-jump"
                onClick={() => {
                  const section = document.getElementById(AFFECTED_ITEMS_ID);
                  section?.scrollIntoView({ block: 'start' });
                  section?.focus();
                }}
              >
                {`${plural(preview.items.length, 'affected item')} ↓`}
              </button>
            </p>
          )}
          {preview.partners.length > 0 && (
            <div>
              <h3 className="app-panel-heading">Partners</h3>
              <ul className="app-terms-partners">
                {preview.partners.map(({ partner, item_count }) => (
                  <li key={partner.id}>
                    <Link
                      to="/partners/$partnerId"
                      params={{ partnerId: String(partner.id) }}
                      className="app-link"
                      target="_blank"
                      rel="noopener"
                    >
                      {partner.name}
                    </Link>
                    <span className="app-muted app-figure">{plural(item_count, 'item')}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

const COLUMNS = ['6.5rem', 'auto', '5rem', '12rem', '10.5rem', '6.5rem', '9.5rem'] as const;

export function AffectedItems({ preview, stale }: { preview: ImpactPreviewOut; stale: boolean }) {
  if (preview.items.length === 0) return null;
  const changing = new Set(preview.changed_fields);
  return (
    <section
      id={AFFECTED_ITEMS_ID}
      tabIndex={-1}
      aria-label="Affected items"
      className="app-terms-affected"
      aria-busy={stale || undefined}
    >
      <h2 className="app-terms-section-title">
        Affected items <span className="app-tp-count">{preview.items.length}</span>
      </h2>
      <div className="app-terms-table-wrap">
        <table className="app-terms-table" aria-label="Affected items">
          <colgroup>
            {COLUMNS.map((width, index) => (
              <col key={index} style={width === 'auto' ? undefined : { width }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Title</th>
              <th scope="col">Live</th>
              <th scope="col">Quotes</th>
              <th scope="col">Will become</th>
              <th scope="col">Lane</th>
              <th scope="col">Numbers</th>
            </tr>
          </thead>
          <tbody>
            {preview.items.map((affected) => {
              const quotes = affected.quoted_fields
                .map((f) => `${TERMS_FIELD_LABELS[f]}${changing.has(f) ? ' (changes)' : ''}`)
                .join(', ');
              const title =
                affected.item.partner === null
                  ? affected.item.title
                  : `${affected.item.title} · ${affected.item.partner.name}`;
              return (
                <tr key={affected.item.id}>
                  <td>
                    <ItemKey value={affected.item.key} />
                  </td>
                  <td className="app-terms-cell-title" title={title}>
                    <Link
                      to="/items/$itemId"
                      params={{ itemId: String(affected.item.id) }}
                      className="app-tp-link"
                      target="_blank"
                      rel="noopener"
                    >
                      {affected.item.title}
                    </Link>
                    {affected.item.partner !== null && (
                      <span className="app-muted"> · {affected.item.partner.name}</span>
                    )}
                  </td>
                  <td>{affected.is_live ? 'Live' : 'Not live'}</td>
                  <td className="app-terms-cell-quotes" title={quotes}>
                    {affected.quoted_fields.map((field, index) => (
                      <span key={field} data-changing={changing.has(field) || undefined}>
                        {index > 0 && ', '}
                        {TERMS_FIELD_LABELS[field]}
                        {changing.has(field) && <span className="sr-only"> (changes)</span>}
                      </span>
                    ))}
                  </td>
                  <td>
                    <StatusBadge status={affected.will_become} />
                  </td>
                  {/* A lane is how a re-review clears; an expired item has none until its next round. */}
                  <td>
                    {affected.will_become !== 'needs_rereview' ? (
                      <span className="app-muted" aria-label="No lane">
                        —
                      </span>
                    ) : affected.lane === 'fast_track' ? (
                      'Fast-track'
                    ) : (
                      'Full review'
                    )}
                  </td>
                  <td className={affected.numbers_change ? undefined : 'app-muted'}>
                    {affected.numbers_change ? 'Numbers change' : 'No number changes'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
