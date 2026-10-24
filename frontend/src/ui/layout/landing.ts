/*
 * Where "/" sends each viewer: the screen their job starts on. Work comes first for someone with several roles
 * (a lead who is also an admin lands on the queue).
 */
import type { Role } from '../domain';

export type Landing = '/queue' | '/mine' | '/import' | '/library';

export function landingFor(roles: readonly Role[]): Landing {
  if (roles.includes('reviewer') || roles.includes('lead')) return '/queue';
  if (roles.includes('marketer')) return '/mine';
  if (roles.includes('admin')) return '/import';
  return '/library';
}
