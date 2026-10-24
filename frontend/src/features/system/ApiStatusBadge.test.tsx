import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getHealthMockHandler } from '../../api/generated/core/core.msw';
import { renderWithQuery } from '../../test/render';
import { server } from '../../test/server';
import { ApiStatusBadge } from './ApiStatusBadge';

describe('ApiStatusBadge', () => {
  it('shows online when the health endpoint reports ok', async () => {
    server.use(getHealthMockHandler({ status: 'ok', database: true }));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByText('API: online')).toBeInTheDocument();
  });

  it('shows unavailable when the health endpoint fails', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.json({ detail: 'down' }, { status: 503 })));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByText('API: unavailable')).toBeInTheDocument();
  });

  it('shows unavailable when the health endpoint reports a non-ok status', async () => {
    server.use(getHealthMockHandler({ status: 'degraded', database: false }));

    renderWithQuery(<ApiStatusBadge />);

    expect(await screen.findByText('API: unavailable')).toBeInTheDocument();
  });
});
