import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
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
