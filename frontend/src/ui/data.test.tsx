import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ItemKey } from './ItemKey';
import { formatAge, RelativeAge } from './RelativeAge';
import { showToast, toastQueue, ToastHost } from './toast';

describe('ItemKey', () => {
  it('renders the key in mono and copies it on press', async () => {
    const user = userEvent.setup();
    render(<ItemKey value="CP-1042" />);
    expect(screen.getByText('CP-1042')).toHaveClass('font-mono');

    await user.click(screen.getByRole('button', { name: 'Copy CP-1042' }));

    expect(await navigator.clipboard.readText()).toBe('CP-1042');
    expect(await screen.findByRole('status')).toHaveTextContent('Copied');
  });

  it("says it couldn't copy when the clipboard rejects, without an unhandled rejection", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValueOnce(new DOMException('denied'));
    render(<ItemKey value="CP-7" />);

    await user.click(screen.getByRole('button', { name: 'Copy CP-7' }));

    expect(await screen.findByRole('status')).toHaveTextContent("Couldn't copy");
  });

  it('can render without the copy control', () => {
    render(<ItemKey value="CP-9" copyable={false} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('formatAge', () => {
  const now = new Date('2026-10-24T12:00:00Z');
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000);

  it.each([
    [0, 'now'],
    [59, 'now'],
    [60, '1m'],
    [59 * 60, '59m'],
    [3600, '1h'],
    [23 * 3600, '23h'],
    [24 * 3600, '1d'],
    [13 * 86400, '13d'],
    [14 * 86400, '2w'],
    [59 * 86400, '8w'],
    [60 * 86400, '2mo'],
    [364 * 86400, '12mo'],
    [365 * 86400, '1y'],
  ])('%is ago is %s', (seconds, expected) => {
    expect(formatAge(ago(seconds), now)).toBe(expected);
  });

  it('clamps a future timestamp (clock skew) to now instead of going negative', () => {
    expect(formatAge(new Date(now.getTime() + 90_000), now)).toBe('now');
  });
});

describe('RelativeAge', () => {
  const now = new Date('2026-10-24T12:00:00Z');

  it('shows compact age with machine-readable time and a spoken absolute time', () => {
    const { container } = render(<RelativeAge at="2026-10-21T12:00:00Z" now={now} />);
    const time = container.querySelector('time');
    expect(time).toHaveAttribute('dateTime', '2026-10-21T12:00:00.000Z');
    expect(time).toHaveTextContent('3d');
    expect(time).toHaveClass('app-age'); // theme.css: tabular-nums, so ages align in columns
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(/Oct 2\d, 2026/);
  });

  it('shows the absolute time as a tooltip on focus', async () => {
    const user = userEvent.setup();
    render(<RelativeAge at="2026-10-21T12:00:00Z" now={now} />);
    await user.tab();
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip.textContent).toMatch(/Oct 2\d, 2026/);
  });

  it('renders an em dash for an invalid timestamp', () => {
    const { container } = render(<RelativeAge at="not a date" now={now} />);
    expect(container).toHaveTextContent('—');
    expect(container.querySelector('time')).toBeNull();
  });
});

describe('toast', () => {
  afterEach(() => {
    act(() => {
      toastQueue.clear();
    });
  });

  it('shows a toast in the notifications region and dismisses it', async () => {
    const user = userEvent.setup();
    render(<ToastHost />);

    act(() => {
      showToast({ title: 'Assigned to you', description: 'CP-1042' });
    });

    const region = await screen.findByRole('region', { name: 'Notifications' });
    expect(region).toHaveTextContent('Assigned to you');
    expect(region).toHaveTextContent('CP-1042');

    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => {
      expect(screen.queryByText('Assigned to you')).toBeNull();
    });
  });

  it('marks error toasts with the error tone and icon', async () => {
    render(<ToastHost />);
    act(() => {
      showToast({ title: "Couldn't save the decision", tone: 'error' });
    });
    const title = await screen.findByText("Couldn't save the decision");
    const toast = title.closest('[data-tone]');
    expect(toast).toHaveAttribute('data-tone', 'error');
    expect(toast?.querySelector('svg[data-icon="feedback.error"]')).not.toBeNull();
  });
});
