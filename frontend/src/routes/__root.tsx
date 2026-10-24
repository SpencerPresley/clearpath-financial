import { createRootRouteWithContext } from '@tanstack/react-router';
import type { QueryClient } from '@tanstack/react-query';

import { AppShell } from '../ui/layout/AppShell';
import { SessionGate } from '../ui/layout/SessionGate';

interface RouterContext {
  queryClient: QueryClient;
}

function Root() {
  return (
    <SessionGate>
      <AppShell />
    </SessionGate>
  );
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: Root,
});
