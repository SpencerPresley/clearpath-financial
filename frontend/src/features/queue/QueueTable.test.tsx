import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ItemRowOut, ItemSort } from '../../api/generated/model';
import { DEFAULT_COLUMN_VISIBILITY } from './columns';
import type { ColumnVisibility, RowSelection } from './columns';
import { makeRow, queueRows } from './fixtures';
import { QueueTable } from './QueueTable';

const NOW = new Date('2026-10-24T15:00:00Z');

function Harness({
  rows = queueRows(NOW),
  sort = 'queue',
  visibility = DEFAULT_COLUMN_VISIBILITY,
  onSortChange = vi.fn(),
  onOpen = vi.fn(),
  onSelection = vi.fn(),
}: {
  rows?: ItemRowOut[];
  sort?: ItemSort;
  visibility?: ColumnVisibility;
  onSortChange?: (sort: ItemSort) => void;
  onOpen?: (id: number) => void;
  onSelection?: (s: RowSelection) => void;
}) {
  const [selection, setSelection] = useState<RowSelection>({});
  const [active, setActive] = useState<number | null>(null);
  return (
    <QueueTable
      rows={rows}
      sort={sort}
      onSortChange={onSortChange}
      activeId={active}
      onActiveChange={setActive}
      onOpen={onOpen}
      rowSelection={selection}
      onRowSelectionChange={(updater) => {
        setSelection((old) => {
          const next = typeof updater === 'function' ? updater(old) : updater;
          onSelection(next);
          return next;
        });
      }}
      columnVisibility={visibility}
      now={NOW}
    />
  );
}

describe('QueueTable', () => {
  it('renders one row per item with the queue columns', () => {
    render(
      <Harness
        rows={[
          makeRow(
            {
              id: 1044,
              title: 'LendStack marketplace tile',
              status: 'submitted',
              risk_tier: 'high',
              partner: { id: 11, name: 'LendStack' },
              assignee: null,
              open_findings_count: 4,
              round: 2,
              submitted_at: '2026-10-21T13:00:00Z',
            },
            NOW,
          ),
        ]}
      />,
    );
    const table = screen.getByRole('table', { name: 'Queue' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(2);
    const r = within(rows[1] ?? table);
    expect(r.getByText('CP-1044')).toBeInTheDocument();
    expect(r.getByText('LendStack marketplace tile')).toBeInTheDocument();
    expect(r.getByText('Submitted')).toBeInTheDocument();
    expect(r.getByText('High risk')).toBeInTheDocument();
    expect(r.getByText('Personal loan')).toBeInTheDocument();
    expect(r.getByText('LendStack')).toBeInTheDocument();
    expect(r.getByText('Unassigned')).toBeInTheDocument();
    expect(r.getByText('4 open findings')).toBeInTheDocument();
    expect(r.getByText('3d')).toBeInTheDocument();
    expect(r.getByText('R2')).toBeInTheDocument();
  });

  it('sorts by title through the server sort and back to queue order', async () => {
    const onSortChange = vi.fn();
    const { rerender } = render(<Harness onSortChange={onSortChange} />);
    await userEvent.click(screen.getByRole('button', { name: /Title/ }));
    expect(onSortChange).toHaveBeenLastCalledWith('title');

    rerender(<Harness sort="title" onSortChange={onSortChange} />);
    expect(screen.getByRole('columnheader', { name: /Title/ })).toHaveAttribute('aria-sort', 'ascending');
    await userEvent.click(screen.getByRole('button', { name: /Title/ }));
    expect(onSortChange).toHaveBeenLastCalledWith('queue');
  });

  it('cycles Age through oldest, newest, and queue order', async () => {
    const onSortChange = vi.fn();
    const { rerender } = render(<Harness onSortChange={onSortChange} />);
    await userEvent.click(screen.getByRole('button', { name: /Age/ }));
    expect(onSortChange).toHaveBeenLastCalledWith('oldest');

    rerender(<Harness sort="oldest" onSortChange={onSortChange} />);
    expect(screen.getByRole('columnheader', { name: /Age/ })).toHaveAttribute('aria-sort', 'descending');
    await userEvent.click(screen.getByRole('button', { name: /Age/ }));
    expect(onSortChange).toHaveBeenLastCalledWith('newest');

    rerender(<Harness sort="newest" onSortChange={onSortChange} />);
    await userEvent.click(screen.getByRole('button', { name: /Age/ }));
    expect(onSortChange).toHaveBeenLastCalledWith('queue');
  });

  it('offers no sort control on columns the server cannot sort', () => {
    render(<Harness />);
    const status = screen.getByRole('columnheader', { name: 'Status' });
    expect(within(status).queryByRole('button')).toBeNull();
    expect(status).not.toHaveAttribute('aria-sort');
  });

  it('hides columns turned off in visibility', () => {
    render(<Harness visibility={{ ...DEFAULT_COLUMN_VISIBILITY, product: false }} />);
    expect(screen.queryByRole('columnheader', { name: 'Product' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: 'Partner' })).toBeInTheDocument();
  });

  it('selects with the checkbox without opening the item', async () => {
    const onOpen = vi.fn();
    const onSelection = vi.fn();
    render(<Harness onOpen={onOpen} onSelection={onSelection} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select CP-1044' }));
    expect(onSelection).toHaveBeenLastCalledWith({ '1044': true });
    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: 'Select CP-1044' })).toBeChecked();
  });

  it('selects every loaded row from the header checkbox', async () => {
    const onSelection = vi.fn();
    render(<Harness onSelection={onSelection} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select all loaded items' }));
    expect(Object.keys(onSelection.mock.lastCall?.[0] as RowSelection)).toHaveLength(8);
  });

  it('opens the item on row click and makes that row the tab stop', async () => {
    const onOpen = vi.fn();
    render(<Harness onOpen={onOpen} />);
    const cell = screen.getByText('RateRadar lead-gen form copy');
    await userEvent.click(cell);
    expect(onOpen).toHaveBeenCalledWith(1047);
    const row = cell.closest('tr');
    expect(row).toHaveAttribute('tabindex', '0');
    expect(row).toHaveAttribute('data-active', 'true');
  });

  it('marks re-reviews with their reason when the column is shown', () => {
    render(<Harness visibility={{ ...DEFAULT_COLUMN_VISIBILITY, reopen_reason: true }} />);
    expect(screen.getByText('Terms changed')).toBeInTheDocument();
  });
});
