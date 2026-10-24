/*
 * Resolves who is signed in from GET /api/me and provides it to the shell (roles drive the nav). Signed out
 * (401) shows the sign-in form; any other failure says so with a retry. Roles are `effective_roles` (granted
 * plus implied, e.g. a lead is also a reviewer), so the UI never re-implements role implication.
 */
import type { ReactNode } from 'react';

import { useGetMe } from '../../api/generated/me/me';
import type { MeOut } from '../../api/generated/model';
import { Button } from '../Button';
import { errorMessage, errorStatus } from '../errorMessage';
import { SignIn } from './SignIn';
import { ViewerProvider } from './Viewer';
import type { Viewer } from './Viewer';

export function viewerFromMe(me: MeOut): Viewer {
  return { id: me.id, name: me.display_name || me.email, email: me.email, roles: me.effective_roles };
}

function isSignedOut(error: unknown): boolean {
  const status = errorStatus(error);
  return status === 401 || status === 403;
}

export function SessionGate({ children }: { children: ReactNode }) {
  const me = useGetMe({
    query: {
      retry: (count, error) => !isSignedOut(error) && count < 2,
      staleTime: 5 * 60_000,
    },
  });

  if (me.isPending) {
    return (
      <div className="app-signin" aria-busy="true" aria-label="Loading">
        <header className="app-topbar" />
      </div>
    );
  }
  if (me.isError) {
    if (isSignedOut(me.error)) {
      return (
        <SignIn
          onSignedIn={() => {
            void me.refetch();
          }}
        />
      );
    }
    return (
      <div className="app-signin">
        <header className="app-topbar" />
        <main className="app-signin-main">
          <div className="app-signin-form" role="alert">
            <h1 className="app-page-title">Couldn’t load your account</h1>
            <p className="text-muted">{errorMessage(me.error, 'The server didn’t answer. Try again.')}</p>
            <Button
              icon="action.reload"
              onPress={() => {
                void me.refetch();
              }}
            >
              Retry
            </Button>
          </div>
        </main>
      </div>
    );
  }
  return <ViewerProvider viewer={viewerFromMe(me.data)}>{children}</ViewerProvider>;
}
