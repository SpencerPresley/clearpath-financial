import { useMutation } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { customFetch } from '../../api/mutator';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { ApiStatusBadge } from './ApiStatusBadge';

describe('ApiStatusBadge', () => {
  it('shows nothing visible when the health endpoint reports ok, and takes no tab stop', async () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));

    const { container } = renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByText('Server connected')).toHaveClass('sr-only');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(container.querySelector('[tabindex]')).toBeNull();
  });

  it('shows nothing visible while the first check is in flight', () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));

    renderWithQuery(<ApiStatusBadge />);

    expect(screen.getByText('Checking server connection')).toHaveClass('sr-only');
  });

  it('alerts visibly, with the consequence, when the health endpoint fails', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.json({ detail: 'down' }, { status: 503 })));

    renderWithQuery(<ApiStatusBadge />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Can't reach server · changes won't save");
  });

  it('alerts visibly when the health endpoint reports a non-ok status', async () => {
    server.use(getHealthMockHandler({ status: 'degraded', database: false }));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach server");
  });
});

function Save() {
  const save = useMutation({ mutationFn: () => customFetch('/api/items/1', { method: 'PATCH' }) });
  return (
    <button
      type="button"
      onClick={() => {
        save.mutate();
      }}
    >
      Save
    </button>
  );
}

describe('ApiStatusBadge after a failed save', () => {
  it.each([
    ['the request never reached the server', () => HttpResponse.error()],
    ['a proxy answered 502', () => new HttpResponse('Bad gateway', { status: 502 })],
  ])('rechecks at once when %s, so the banner shows with the failing toast', async (_, failure) => {
    let up = true;
    server.use(
      http.get('*/api/health', () =>
        up
          ? HttpResponse.json({ status: 'ok', database: true })
          : HttpResponse.json({ detail: 'down' }, { status: 503 }),
      ),
      http.patch('*/api/items/1', failure),
    );
    renderWithQuery(
      <>
        <ApiStatusBadge />
        <Save />
      </>,
    );
    expect(await screen.findByText('Server connected')).toBeInTheDocument();

    up = false;
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    // Well before the 30 s poll.
    expect(await screen.findByRole('alert', {}, { timeout: 1000 })).toHaveTextContent("Can't reach server");
  });

  it("doesn't recheck on a refusal: a 4xx came from a server that's up", async () => {
    let checks = 0;
    server.use(
      http.get('*/api/health', () => {
        checks += 1;
        return HttpResponse.json({ status: 'ok', database: true });
      }),
      http.patch('*/api/items/1', () => HttpResponse.json({ message: 'No.' }, { status: 403 })),
    );
    renderWithQuery(
      <>
        <ApiStatusBadge />
        <Save />
      </>,
    );
    expect(await screen.findByText('Server connected')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(checks).toBe(1);
  });
});
