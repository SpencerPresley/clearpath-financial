import type { Role } from '../../api/generated/model';

/** Short role names for the Users table and form ("Lead" is the compliance lead). */
export const ROLE_NAMES: Record<Role, string> = {
  marketer: 'Marketer',
  reviewer: 'Reviewer',
  lead: 'Lead',
  admin: 'Admin',
};

/** Roles whose work auto-assignment hands out, so availability means something for them. */
export function doesReviewWork(roles: readonly Role[]): boolean {
  return roles.includes('reviewer') || roles.includes('lead');
}
