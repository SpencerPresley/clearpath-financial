import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { useHotkeys } from './useHotkeys';

function Harness({ onN, enabled = true }: { onN: () => void; enabled?: boolean }) {
  useHotkeys({ n: onN, '?': onN }, enabled);
  return (
    <div>
      <button type="button">Focusable</button>
      <textarea aria-label="Reason" />
      <input aria-label="Name" />
    </div>
  );
}

describe('useHotkeys', () => {
  it('fires on the page', async () => {
    const onN = vi.fn();
    render(<Harness onN={onN} />);
    await userEvent.keyboard('n');
    await userEvent.keyboard('?');
    expect(onN).toHaveBeenCalledTimes(2);
  });

  it('ignores keys typed into text fields', async () => {
    const onN = vi.fn();
    render(<Harness onN={onN} />);
    await userEvent.type(screen.getByLabelText('Reason'), 'nnn');
    await userEvent.type(screen.getByLabelText('Name'), 'n');
    expect(onN).not.toHaveBeenCalled();
  });

  it('ignores modified keys and respects enabled', async () => {
    const onN = vi.fn();
    const { rerender } = render(<Harness onN={onN} />);
    await userEvent.keyboard('{Meta>}n{/Meta}');
    expect(onN).not.toHaveBeenCalled();
    rerender(<Harness onN={onN} enabled={false} />);
    await userEvent.keyboard('n');
    expect(onN).not.toHaveBeenCalled();
  });

  it('stays quiet while a dialog is open', async () => {
    const onN = vi.fn();
    render(
      <>
        <Harness onN={onN} />
        <div role="dialog" aria-modal="true" />
      </>,
    );
    await userEvent.keyboard('n');
    expect(onN).not.toHaveBeenCalled();
  });

  it('keeps working while a toast is showing (RAC toasts are non-modal alertdialogs)', async () => {
    const onN = vi.fn();
    render(
      <>
        <Harness onN={onN} />
        <div role="alertdialog" aria-modal="false" />
      </>,
    );
    await userEvent.keyboard('n');
    expect(onN).toHaveBeenCalledTimes(1);
  });
});
