import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { ApiStatusBadge } from './ApiStatusBadge';

describe('ApiStatusBadge', () => {
  it('stays quiet when the health endpoint reports ok: named for screen readers only', async () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));

    renderWithQuery(<ApiStatusBadge />);

    const indicator = await screen.findByRole('img', { name: 'API online' });
    expect(indicator).not.toHaveTextContent('API online'); // glyph only, no visible text
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows nothing visible while the first check is in flight', () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));

    renderWithQuery(<ApiStatusBadge />);

    expect(screen.getByText('Checking API')).toHaveClass('sr-only');
  });

  it('alerts visibly when the health endpoint fails', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.json({ detail: 'down' }, { status: 503 })));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable');
  });

  it('alerts visibly when the health endpoint reports a non-ok status', async () => {
    server.use(getHealthMockHandler({ status: 'degraded', database: false }));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable');
  });
});
