import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from './Button';
import { EmptyState } from './EmptyState';
import { SkeletonBadge, SkeletonTable, SkeletonText } from './Skeleton';

describe('EmptyState', () => {
  it('says why it is empty and offers the next action (spec §5.5)', () => {
    render(
      <EmptyState icon="nav.queue" title="Nothing assigned to you" action={<Button>Show unassigned</Button>}>
        4 unassigned items
      </EmptyState>,
    );
    expect(screen.getByRole('heading', { name: 'Nothing assigned to you' })).toBeInTheDocument();
    expect(screen.getByText('4 unassigned items')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show unassigned' })).toBeInTheDocument();
  });

  it('renders without detail or action', () => {
    const { container } = render(<EmptyState icon="entity.finding" title="No findings" />);
    expect(container.querySelector('.app-empty-action')).toBeNull();
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('Skeleton', () => {
  it('renders the requested rows and columns, busy, with one spoken label', () => {
    const { container } = render(
      <SkeletonTable rows={4} columns={['6rem', '1fr', '7rem']} label="Loading queue" />,
    );
    const table = screen.getByRole('status', { name: 'Loading queue' });
    expect(table).toHaveAttribute('aria-busy', 'true');
    expect(container.querySelectorAll('.app-skeleton-row')).toHaveLength(4);
    const firstRow = container.querySelector('.app-skeleton-row');
    expect(firstRow?.children).toHaveLength(3);
    expect(firstRow).toHaveAttribute('aria-hidden', 'true');
  });

  it('sizes text and badge placeholders from props', () => {
    const { container } = render(
      <>
        <SkeletonText width="12rem" />
        <SkeletonBadge />
      </>,
    );
    expect(container.querySelector<HTMLElement>('.app-skeleton')?.style.width).toBe('12rem');
    expect(container.querySelector('.app-skeleton-badge')).toBeInTheDocument();
  });
});
