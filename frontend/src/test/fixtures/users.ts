/*
 * People for the Users screen, the assignee pickers, and the lead's workload panel: the seeded review team
 * (docs/demo.md), with Leah out of office. Pure data, no MSW, so Playwright can import it.
 */
import type { UserOut, WorkloadOut } from '../../api/generated/model';

function user(
  id: number,
  display_name: string,
  roles: UserOut['roles'],
  extra: Partial<UserOut> = {},
): UserOut {
  const first = display_name.split(' ')[0]?.toLowerCase() ?? 'user';
  return {
    id,
    email: `${first}@clearpath.demo`,
    display_name,
    roles,
    is_available: true,
    is_active: true,
    ...extra,
  };
}

/** Morgan Admin is ME_ADMIN (id 1), the only admin. */
export const TEAM: UserOut[] = [
  user(1, 'Morgan Admin', ['admin']),
  user(2, 'Dana Kim', ['reviewer']),
  user(3, 'Leah Brandt', ['reviewer'], { is_available: false }),
  user(4, 'Nikhil Rao', ['reviewer']),
  user(5, 'Priya Natarajan', ['marketer']),
  user(6, 'Rachel Okafor', ['lead']),
  user(7, 'Samuel Ortega', ['reviewer']),
  user(8, 'Old Contractor', ['reviewer'], { is_active: false }),
];

export const REVIEWERS: UserOut[] = TEAM.filter((u) => u.is_active && u.roles.includes('reviewer'));

/** GET /users/workload: heaviest first, as reviews.assignment.weighted_loads counts it. */
export const WORKLOAD: WorkloadOut[] = [
  {
    user_id: 7,
    name: 'Samuel Ortega',
    is_available: true,
    auto_assigned: true,
    open_items: 6,
    weighted_load: 13,
  },
  { user_id: 2, name: 'Dana Kim', is_available: true, auto_assigned: true, open_items: 4, weighted_load: 9 },
  {
    user_id: 6,
    name: 'Rachel Okafor',
    is_available: true,
    auto_assigned: false,
    open_items: 1,
    weighted_load: 3,
  },
  {
    user_id: 4,
    name: 'Nikhil Rao',
    is_available: true,
    auto_assigned: true,
    open_items: 1,
    weighted_load: 2,
  },
  {
    user_id: 3,
    name: 'Leah Brandt',
    is_available: false,
    auto_assigned: false,
    open_items: 0,
    weighted_load: 0,
  },
];
