import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { STATUS_META } from '../badges';
import { ITEM_STATUSES } from '../domain';
import { icons } from '../icons';
import type { IconKey } from '../icons';
import { DesignGallery } from './DesignGallery';

describe('DesignGallery', () => {
  it('shows every item status', () => {
    render(<DesignGallery />);
    const section = screen.getByRole('region', { name: 'Status' });
    for (const status of ITEM_STATUSES) {
      expect(within(section).getAllByText(STATUS_META[status].label).length).toBeGreaterThan(0);
    }
  });

  it('shows every icon registry key', () => {
    const { container } = render(<DesignGallery />);
    const section = screen.getByRole('region', { name: 'Icons' });
    for (const key of Object.keys(icons) as IconKey[]) {
      expect(within(section).getByText(key)).toBeInTheDocument();
    }
    expect(container.querySelectorAll('[data-icon]').length).toBeGreaterThan(Object.keys(icons).length);
  });

  it('shows every button variant, enabled and disabled', () => {
    render(<DesignGallery />);
    const section = screen.getByRole('region', { name: 'Buttons' });
    for (const variant of ['primary', 'secondary', 'ghost', 'danger']) {
      const buttons = within(section)
        .getAllByRole('button')
        .filter((button) => button.dataset.variant === variant);
      expect(buttons.some((button) => button.hasAttribute('data-disabled'))).toBe(true);
      expect(buttons.some((button) => !button.hasAttribute('data-disabled'))).toBe(true);
    }
  });
});
