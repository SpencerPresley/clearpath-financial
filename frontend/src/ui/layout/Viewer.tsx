/*
 * Who is using the app, as far as the UI needs to know: id (ownership checks), name for the user menu, and
 * effective roles for the nav and role-gated controls. SessionGate (root route) resolves it from GET /api/me.
 */
import { createContext, use } from 'react';
import type { ReactNode } from 'react';

import type { Role } from '../domain';

export interface Viewer {
  id: number;
  name: string;
  email: string;
  /** Effective roles (granted plus implied: a lead is also a reviewer). */
  roles: readonly Role[];
}

const ViewerContext = createContext<Viewer | null>(null);

export function ViewerProvider({ viewer, children }: { viewer: Viewer; children: ReactNode }) {
  return <ViewerContext value={viewer}>{children}</ViewerContext>;
}

export function useViewer(): Viewer {
  const viewer = use(ViewerContext);
  if (viewer === null) {
    throw new Error('useViewer needs a ViewerProvider (SessionGate provides it in the app).');
  }
  return viewer;
}

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1] ?? '') : '';
  return (last === '' ? first.slice(0, 2) : first.charAt(0) + last.charAt(0)).toUpperCase();
}
