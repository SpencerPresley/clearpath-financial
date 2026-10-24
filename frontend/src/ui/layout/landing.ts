/*
 * Where "/" sends each viewer: the screen their job starts on. Work comes first for someone with several roles
 * (a lead who is also an admin lands on the queue). Also where sign-in sends them (ledger: landing route by
 * role), unless they arrived on a link to a screen they can open.
 */
import type { Role } from '../domain';
import { NAV_SECTIONS } from './nav';

export type Landing = '/queue' | '/mine' | '/import' | '/library';

export function landingFor(roles: readonly Role[]): Landing {
  if (roles.includes('reviewer') || roles.includes('lead')) return '/queue';
  if (roles.includes('marketer')) return '/mine';
  if (roles.includes('admin')) return '/import';
  return '/library';
}

/** Metrics reads are allowed to reviewers (so leads) and admins (backend metrics selectors), wider than the nav. */
export const METRICS_ROLES: readonly Role[] = ['reviewer', 'lead', 'admin'];

/** Who may open a section's pages, by its first path segment; New submission shares the marketer's area. */
function sectionRoles(segment: string): readonly Role[] | 'everyone' | undefined {
  if (segment === 'metrics') return METRICS_ROLES;
  if (segment === 'mine') return NAV_SECTIONS.find((s) => s.to === '/mine')?.roles;
  return NAV_SECTIONS.find((s) => s.to === `/${segment}`)?.roles;
}

/**
 * Whether these roles can open the screen at `pathname`. Screens outside the nav's sections (an item, `/`, the
 * design gallery) count as open: the item page itself says when the server refuses or can't find it.
 */
export function canOpen(pathname: string, roles: readonly Role[]): boolean {
  const segment = pathname.split('/')[1] ?? '';
  const allowed = sectionRoles(segment);
  if (allowed === undefined || allowed === 'everyone') return true;
  return allowed.some((role) => roles.includes(role));
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
