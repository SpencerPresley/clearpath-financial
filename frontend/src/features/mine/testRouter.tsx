/*
 * Test-only: mounts a page in a memory-history router with a stub `/items/$itemId` route, so pages that
 * navigate or render Links work without booting the app shell. Returns the router so tests can assert
 * where a submit landed.
 */
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router';
import type { ComponentType } from 'react';

import { renderWithQuery } from '../../test/render';

export function renderAtRoute(Page: ComponentType, { path, url }: { path: string; url?: string }) {
  const root = createRootRoute({ component: Outlet });
  const page = createRoute({ getParentRoute: () => root, path, component: () => <Page /> });
  const review = createRoute({
    getParentRoute: () => root,
    path: '/items/$itemId',
    component: () => <p>Review screen</p>,
  });
  const router = createRouter({
    routeTree: root.addChildren([page, review]),
    history: createMemoryHistory({ initialEntries: [url ?? path] }),
  });
  const result = renderWithQuery(<RouterProvider router={router} />);
  return { router, ...result };
}
