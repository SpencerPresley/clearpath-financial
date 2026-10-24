/*
 * What publishing would do (F's ImpactPreviewOut): the summary sentence as the server wrote it, the counts, the
 * fields quoted copy uses that change, the partners, and every affected item. "Will need re-review" carries
 * the alert tone because it is that status (spec §5.2); live/not live, lane, and partner are facts, uncolored.
 */
import { Link } from '@tanstack/react-router';

import type { ImpactPreviewOut } from '../../api/generated/model';
import { StatusBadge, StatusMark } from '../../ui/badges';
import { ItemKey } from '../../ui/ItemKey';
import { plural } from '../../ui/labels';
import { SkeletonText } from '../../ui/Skeleton';
import { TERMS_FIELD_LABELS } from './termsForm';

function Count({
  value,
  label,
  mark,
}: {
  value: number;
  label: string;
  mark?: 'needs_rereview' | 'expired';
}) {
  return (
    <div role="group" aria-label={`${String(value)} ${label}`} className="app-terms-count">
      <span className="app-terms-count-figure">{value}</span>
      <span className="app-terms-count-label">
        {mark !== undefined && <StatusMark status={mark} />}
        {label}
      </span>
    </div>
  );
}

export function ImpactPanel({
  nextVersion,
  preview,
  stale,
  loading,
}: {
  nextVersion: number;
  preview: ImpactPreviewOut | undefined;
  /** The preview on screen is for earlier values; the next one is loading. */
  stale: boolean;
  loading: boolean;
}) {
  return (
    <section
      aria-label={`Impact of publishing v${String(nextVersion)}`}
      aria-busy={stale && preview !== undefined ? true : undefined}
      className="app-terms-impact"
    >
      <h2 className="app-terms-section-title">Impact</h2>
      {loading ? (
        <div role="status" aria-label="Checking the impact" className="app-panel-skeleton">
          <SkeletonText width="90%" />
          <SkeletonText width="60%" />
          <SkeletonText width="75%" />
        </div>
      ) : preview === undefined ? (
        <p className="app-muted">
          Change a value to see which approved items and partners quote these terms before you publish.
        </p>
      ) : (
        <div className="app-terms-impact-body">
          <p className="app-terms-summary">{preview.summary}</p>
          <div className="app-terms-counts">
            <Count value={preview.will_need_rereview} label="Will need re-review" mark="needs_rereview" />
            <Count value={preview.will_expire} label="Will expire" mark="expired" />
            <Count value={preview.already_in_rereview} label="Already in re-review" />
            <Count value={preview.normal_lane} label="Full review (no fast-track)" />
          </div>
          {preview.changed_fields.length > 0 && (
            <p className="app-terms-impact-line">
              <span className="app-muted">Quoted fields that change: </span>
              {preview.changed_fields.map((field) => TERMS_FIELD_LABELS[field]).join(', ')}
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

const COLUMNS = ['6.5rem', 'auto', '5rem', '12rem', '8.5rem', '6.5rem', '9.5rem'] as const;

export function AffectedItems({ preview, stale }: { preview: ImpactPreviewOut; stale: boolean }) {
  if (preview.items.length === 0) return null;
  const changing = new Set(preview.changed_fields);
  return (
    <section className="app-terms-affected" aria-busy={stale || undefined}>
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
            {preview.items.map((affected) => (
              <tr key={affected.item.id}>
                <td>
                  <ItemKey value={affected.item.key} />
                </td>
                <td className="app-terms-cell-title">
                  <Link
                    to="/items/$itemId"
                    params={{ itemId: String(affected.item.id) }}
                    className="app-tp-link"
                  >
                    {affected.item.title}
                  </Link>
                  {affected.item.partner !== null && (
                    <span className="app-muted"> · {affected.item.partner.name}</span>
                  )}
                </td>
                <td>{affected.is_live ? 'Live' : 'Not live'}</td>
                <td className="app-terms-cell-quotes">
                  {affected.quoted_fields.map((field, index) => (
                    <span key={field} data-changing={changing.has(field) || undefined}>
                      {index > 0 && ', '}
                      {TERMS_FIELD_LABELS[field]}
                    </span>
                  ))}
                </td>
                <td>
                  <StatusBadge status={affected.will_become} />
                </td>
                <td>{affected.lane === 'fast_track' ? 'Fast-track' : 'Full review'}</td>
                <td className={affected.numbers_change ? undefined : 'app-muted'}>
                  {affected.numbers_change ? 'Numbers change' : 'No number changes'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
