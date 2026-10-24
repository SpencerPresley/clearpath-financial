import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Icon } from './Icon';

describe('Icon', () => {
  it('is hidden from assistive tech when it decorates a label', () => {
    const { container } = render(<Icon name="status.approved" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('data-icon', 'status.approved');
    expect(svg).toHaveAttribute('width', '16');
  });

  it('is a named image when it stands alone', () => {
    render(<Icon name="action.filter" label="Filter" size={20} />);
    const img = screen.getByRole('img', { name: 'Filter' });
    expect(img).toHaveAttribute('width', '20');
    expect(img).not.toHaveAttribute('aria-hidden');
  });

  it('uses the registry weight unless overridden', () => {
    const { container, rerender } = render(<Icon name="source.code" />);
    expect(container.querySelector('svg')).toHaveAttribute('data-weight', 'fill');
    rerender(<Icon name="source.code" weight="regular" />);
    expect(container.querySelector('svg')).toHaveAttribute('data-weight', 'regular');
  });
});
