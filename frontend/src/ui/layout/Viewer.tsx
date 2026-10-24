/*
 * Who is using the app, as far as the shell needs to know (name for the user menu, roles for the nav).
 *
 * There is no session/current-user endpoint yet, so the default viewer is an explicit demo viewer with
 * all four roles, and the user menu says so. When /api/me lands, the root route provides the real
 * viewer through ViewerProvider and DEMO_VIEWER goes away.
 */
import { createContext, use } from 'react';
import type { ReactNode } from 'react';

import { ROLES } from '../domain';
import type { Role } from '../domain';

export interface Viewer {
  /** User id; null only for the demo fallback. */
  id: number | null;
  name: string;
  email: string;
  /** Effective roles (granted plus implied: a lead is also a reviewer). */
  roles: readonly Role[];
  /** True only for the fallback viewer; the user menu shows it. */
  isDemo?: boolean;
}

export const DEMO_VIEWER: Viewer = { id: null, name: 'Demo user', email: '', roles: ROLES, isDemo: true };

const ViewerContext = createContext<Viewer>(DEMO_VIEWER);

export function ViewerProvider({ viewer, children }: { viewer: Viewer; children: ReactNode }) {
  return <ViewerContext value={viewer}>{children}</ViewerContext>;
}

export function useViewer(): Viewer {
  return use(ViewerContext);
}

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1] ?? '') : '';
  return (last === '' ? first.slice(0, 2) : first.charAt(0) + last.charAt(0)).toUpperCase();
}
