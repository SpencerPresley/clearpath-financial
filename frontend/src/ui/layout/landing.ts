/*
 * Where "/" sends each viewer: the screen their job starts on. Work comes first for someone with several roles
 * (a lead who is also an admin lands on the queue). Also where sign-in sends them (ledger: landing route by
 * role), unless they arrived on a link to a screen they can open.
 */
import type { Role } from '../domain';

export type Landing = '/queue' | '/mine' | '/import' | '/library';

export function landingFor(roles: readonly Role[]): Landing {
  if (roles.includes('reviewer') || roles.includes('lead')) return '/queue';
  if (roles.includes('marketer')) return '/mine';
  if (roles.includes('admin')) return '/import';
  return '/library';
}

/**
 * Pages only some roles can use, by first path segment, matching what the server allows (not the nav, which
 * is narrower: Metrics is in a lead's nav, but reviewers and admins may read it). Every other page is open to
 * anyone signed in: Library, Outbox, and the read-only Offer terms and Partners; an item page shows the server's
 * own 403 or 404.
 */
export const PAGE_ROLES = {
  queue: ['reviewer', 'lead'],
  mine: ['marketer'],
  submit: ['marketer'],
  import: ['admin'],
  metrics: ['reviewer', 'lead', 'admin'],
} as const satisfies Record<string, readonly Role[]>;

export const LANDING_LABELS: Record<Landing, string> = {
  '/queue': 'Queue',
  '/mine': 'My submissions',
  '/import': 'Import',
  '/library': 'Library',
};

export function hasAnyRole(roles: readonly Role[], allowed: readonly Role[]): boolean {
  return allowed.some((role) => roles.includes(role));
}

/** Whether these roles can use the page at `pathname`. */
export function canOpen(pathname: string, roles: readonly Role[]): boolean {
  const segment = pathname.split('/')[1] ?? '';
  const allowed: readonly Role[] | undefined = (PAGE_ROLES as Record<string, readonly Role[]>)[segment];
  return allowed === undefined || hasAnyRole(roles, allowed);
}

/**
 * Where to go once signed in, or null to stay. A different person than the one last signed in to this tab
 * always starts at their landing: the URL is the previous user's screen, not a link this person followed.
 */
export function afterSignIn({
  pathname,
  roles,
  userChanged,
}: {
  pathname: string;
  roles: readonly Role[];
  userChanged: boolean;
}): Landing | null {
  if (pathname === '/' || userChanged || !canOpen(pathname, roles)) return landingFor(roles);
  return null;
}
