import { createRootRouteWithContext, useRouter } from '@tanstack/react-router';
import type { QueryClient } from '@tanstack/react-query';

import { AppShell } from '../ui/layout/AppShell';
import { afterSignIn } from '../ui/layout/landing';
import { SessionGate } from '../ui/layout/SessionGate';

interface RouterContext {
  queryClient: QueryClient;
}

function Root() {
  const router = useRouter();
  return (
    <SessionGate
      onSignedIn={async (me, userChanged) => {
        const target = afterSignIn({
          pathname: router.state.location.pathname,
          roles: me.effective_roles,
          userChanged,
        });
        if (target !== null) await router.navigate({ to: target, replace: true });
      }}
    >
      <AppShell />
    </SessionGate>
  );
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: Root,
});
