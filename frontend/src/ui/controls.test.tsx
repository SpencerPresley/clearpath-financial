import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from './Button';
import { IconButton } from './IconButton';
import { Kbd } from './Kbd';
import { Tooltip } from './Tooltip';

describe('Button', () => {
  it('fires onPress and defaults to the secondary variant', async () => {
    const onPress = vi.fn();
    render(<Button onPress={onPress}>Assign</Button>);
    const button = screen.getByRole('button', { name: 'Assign' });
    expect(button).toHaveAttribute('data-variant', 'secondary');
    await userEvent.click(button);
    expect(onPress).toHaveBeenCalledOnce();
  });

  it.each(['primary', 'secondary', 'ghost', 'danger'] as const)('renders the %s variant', (variant) => {
    render(<Button variant={variant}>Go</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('data-variant', variant);
  });

  it('does not fire when disabled', async () => {
    const onPress = vi.fn();
    render(
      <Button isDisabled onPress={onPress}>
        Reject
      </Button>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('renders a leading registry icon, hidden from assistive tech', () => {
    render(<Button icon="action.approve">Approve</Button>);
    const button = screen.getByRole('button', { name: 'Approve' });
    expect(button.querySelector('svg[data-icon="action.approve"]')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('IconButton', () => {
  it('is named by its aria-label and shows the same text as a tooltip on focus', async () => {
    const user = userEvent.setup();
    render(<IconButton icon="action.filter" aria-label="Filter" />);
    const button = screen.getByRole('button', { name: 'Filter' });
    await user.tab();
    expect(button).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Filter');
  });

  it('can opt out of the tooltip', async () => {
    const user = userEvent.setup();
    render(<IconButton icon="action.close" aria-label="Close" tooltip={false} />);
    await user.tab();
    expect(screen.queryByRole('tooltip')).toBeNull();
  });
});

describe('Tooltip', () => {
  it('shows content on keyboard focus of its trigger', async () => {
    const user = userEvent.setup();
    render(
      <Tooltip content="Assign to me">
        <Button>Claim</Button>
      </Tooltip>,
    );
    await user.tab();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Assign to me');
  });
});

describe('Kbd', () => {
  it('renders one <kbd> per key inside a labelled group', () => {
    const { container } = render(<Kbd keys={['Shift', 'A']} />);
    expect(container.querySelectorAll('kbd kbd')).toHaveLength(2);
    expect(container.querySelector('kbd')).toHaveTextContent('ShiftA');
  });
});
