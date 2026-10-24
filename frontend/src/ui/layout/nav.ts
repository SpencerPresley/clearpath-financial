/*
 * Primary navigation model. Sections and who sees them come from product-spec.md (Roles, Screens).
 * A user's roles are a list; they see the union of sections, in this file's order.
 *
 * `to` is set only once the section's route exists. Until then the shell renders it disabled rather
 * than linking to a placeholder page (no fake behavior). Workstreams I/J add `to` as they ship screens.
 */
import type { LinkProps } from '@tanstack/react-router';

import type { Role } from '../domain';
import type { IconKey } from '../icons';

export type NavGroupId = 'work' | 'reference' | 'operations';

export interface NavSection {
  id: string;
  label: string;
  icon: IconKey;
  group: NavGroupId;
  /** Roles that see this section; 'everyone' includes users with no roles. */
  roles: readonly Role[] | 'everyone';
  to: LinkProps['to'];
}

export const NAV_GROUPS: readonly { id: NavGroupId; label: string }[] = [
  { id: 'work', label: 'Work' },
  { id: 'reference', label: 'Reference' },
  { id: 'operations', label: 'Operations' },
];

export const NAV_SECTIONS: readonly NavSection[] = [
  {
    id: 'queue',
    label: 'Queue',
    icon: 'nav.queue',
    group: 'work',
    roles: ['reviewer', 'lead'],
    to: '/queue',
  },
  {
    id: 'my-submissions',
    label: 'My submissions',
    icon: 'nav.my_submissions',
    group: 'work',
    roles: ['marketer'],
    to: '/mine',
  },
  {
    id: 'new-submission',
    label: 'New submission',
    icon: 'nav.new_submission',
    group: 'work',
    roles: ['marketer'],
    to: '/submit',
  },
  {
    id: 'library',
    label: 'Library',
    icon: 'nav.library',
    group: 'reference',
    roles: 'everyone',
    to: '/library',
  },
  {
    id: 'offer-terms',
    label: 'Offer terms',
    icon: 'nav.offer_terms',
    group: 'reference',
    roles: ['reviewer', 'lead'],
    to: '/terms',
  },
  {
    id: 'partners',
    label: 'Partners',
    icon: 'nav.partners',
    group: 'reference',
    roles: ['reviewer', 'lead'],
    to: '/partners',
  },
  {
    id: 'metrics',
    label: 'Metrics',
    icon: 'nav.metrics',
    group: 'operations',
    // Admins read metrics too (the API allows reviewer, lead and admin; walkthrough S16).
    roles: ['lead', 'admin'],
    to: '/metrics',
  },
  { id: 'import', label: 'Import', icon: 'nav.import', group: 'operations', roles: ['admin'], to: '/import' },
  { id: 'users', label: 'Users', icon: 'nav.users', group: 'operations', roles: ['admin'], to: '/users' },
  {
    id: 'outbox',
    label: 'Outbox',
    icon: 'nav.outbox',
    group: 'operations',
    roles: 'everyone',
    to: '/outbox',
  },
];

export function navSectionsFor(roles: readonly Role[]): NavSection[] {
  return NAV_SECTIONS.filter(
    (section) => section.roles === 'everyone' || section.roles.some((role) => roles.includes(role)),
  );
}

export function navGroupsFor(
  roles: readonly Role[],
): { id: NavGroupId; label: string; sections: NavSection[] }[] {
  const visible = navSectionsFor(roles);
  return NAV_GROUPS.map((group) => ({
    ...group,
    sections: visible.filter((section) => section.group === group.id),
  })).filter((group) => group.sections.length > 0);
}
