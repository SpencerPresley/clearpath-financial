/*
 * Workload by reviewer (spec §1, Compliance lead: workload balance), for leads, under the stats strip. Collapsed
 * it's one line ("12 open · heaviest Samuel Ortega, load 13"); open, a row per reviewer, heaviest first.
 *
 * The numbers are GET /users/workload, which reads reviews.assignment.weighted_loads: the same load lowest-load
 * assignment ranks by (high 3, medium 2, low 1 per item in the queue), so the panel shows why the next item goes
 * where it goes. A panel rather than a "By reviewer" toggle on the strip: every strip figure opens the list it is
 * the total of (ledger ruling), and a weighted load has no such list. Here only the Open count is a link, and it
 * opens exactly those items (In queue + that assignee).
 */
import { useState } from 'react';
import { Button as AriaButton } from 'react-aria-components';

import type { WorkloadOut } from '../../api/generated/model';
import { useGetReviewerWorkload } from '../../api/generated/users/users';
import { AwayMark } from '../../ui/Availability';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { plural } from '../../ui/labels';
import { viewSearch } from './search';
import type { QueueSearch } from './search';

const OPEN_KEY = 'clearpath.queue.workload';

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === 'open';
  } catch {
    return false;
  }
}

function writeOpen(open: boolean) {
  try {
    window.localStorage.setItem(OPEN_KEY, open ? 'open' : 'closed');
  } catch {
    // Private mode: the panel just doesn't remember.
  }
}

function summary(rows: readonly WorkloadOut[]): string {
  const open = rows.reduce((n, r) => n + r.open_items, 0);
  const heaviest = rows[0];
  if (heaviest === undefined || heaviest.weighted_load === 0) return `${String(open)} open`;
  return `${String(open)} open · heaviest ${heaviest.name}, load ${String(heaviest.weighted_load)}`;
}

function PoolCell({ row }: { row: WorkloadOut }) {
  if (!row.is_available) return <AwayMark />;
  if (!row.auto_assigned) return <span className="text-muted">Not auto-assigned</span>;
  return <span className="text-muted">Gets new work</span>;
}

export function WorkloadPanel({ onPick }: { onPick: (search: QueueSearch) => void }) {
  const [open, setOpen] = useState(readOpen);
  const workload = useGetReviewerWorkload();
  const rows = workload.data ?? [];
  const max = Math.max(1, ...rows.map((r) => r.weighted_load));

  return (
    <section className="app-workload" aria-label="Workload" data-open={open || undefined}>
      <div className="app-workload-head">
        <AriaButton
          className="app-workload-toggle"
          aria-expanded={open}
          aria-controls="workload-table"
          onPress={() => {
            setOpen(!open);
            writeOpen(!open);
          }}
        >
          <Icon name="action.expand" size={14} className="app-workload-caret" />
          <span className="app-workload-title">Workload by reviewer</span>
        </AriaButton>
        <span className="app-workload-summary" aria-live="polite">
          {workload.data !== undefined && summary(rows)}
        </span>
      </div>
      {open && (
        <div id="workload-table" className="app-workload-body">
          {workload.isError ? (
            <span className="app-inline-error" role="alert">
              <Icon name="feedback.error" size={14} />
              <span>Couldn&apos;t load the workload.</span>
              <Button
                size="sm"
                variant="ghost"
                onPress={() => {
                  void workload.refetch();
                }}
              >
                Retry
              </Button>
            </span>
          ) : workload.isPending ? (
            <span className="app-skeleton h-6 w-64" role="status" aria-label="Loading the workload" />
          ) : rows.length === 0 ? (
            <p className="text-ui text-muted">No one holds the reviewer role.</p>
          ) : (
            <table className="app-workload-table" aria-label="Workload by reviewer">
              <thead>
                <tr>
                  <th scope="col">Reviewer</th>
                  <th scope="col" className="app-workload-num">
                    Open
                  </th>
                  <th scope="col">Load</th>
                  <th scope="col">New work</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.user_id}>
                    <th scope="row">{row.name}</th>
                    <td className="app-workload-num">
                      {row.open_items === 0 ? (
                        <span className="text-muted">0</span>
                      ) : (
                        <AriaButton
                          className="app-workload-link"
                          aria-label={`${plural(row.open_items, 'open item')} for ${row.name}`}
                          onPress={() => {
                            onPick({ ...viewSearch('queue'), assignee_id: [row.user_id] });
                          }}
                        >
                          {row.open_items}
                        </AriaButton>
                      )}
                    </td>
                    <td>
                      <span className="app-workload-load">
                        <span className="app-workload-figure">{row.weighted_load}</span>
                        <span className="app-workload-bar" aria-hidden="true">
                          <span style={{ width: `${String((row.weighted_load / max) * 100)}%` }} />
                        </span>
                      </span>
                    </td>
                    <td>
                      <PoolCell row={row} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {workload.data !== undefined && rows.length > 0 && (
            <p className="app-workload-key">
              Load counts each open item by risk: high 3, medium 2, low 1. New items go to the lowest load
              among reviewers who get new work.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
