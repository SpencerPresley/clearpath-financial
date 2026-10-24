import { describe, expect, it } from 'vitest';

import type { Role } from '../domain';
import { afterSignIn, canOpen, landingFor } from './landing';

describe('landingFor', () => {
  it.each<[readonly Role[], string]>([
    [['reviewer'], '/queue'],
    [['lead', 'reviewer'], '/queue'],
    [['marketer'], '/mine'],
    [['admin'], '/import'],
    [['lead', 'reviewer', 'admin'], '/queue'],
    [['marketer', 'admin'], '/mine'],
    [[], '/library'],
  ])('sends %j to %s', (roles, landing) => {
    expect(landingFor(roles)).toBe(landing);
  });
});

describe('canOpen', () => {
  it.each<[string, readonly Role[], boolean]>([
    ['/queue', ['reviewer'], true],
    ['/queue', ['marketer'], false],
    ['/mine', ['marketer'], true],
    ['/mine/12/resubmit', ['reviewer'], false],
    ['/submit', ['admin'], false],
    ['/import', ['admin'], true],
    ['/import', ['lead', 'reviewer'], false],
    // Offer terms and partners are read-only for everyone signed in (the nav shows them to reviewers only).
    ['/terms', ['marketer'], true],
    ['/partners/3', ['marketer'], true],
    ['/queue', ['admin'], false],
    // Metrics reads are open to reviewers, leads and admins (backend metrics selectors), wider than the nav.
    ['/metrics', ['reviewer'], true],
    ['/metrics', ['admin'], true],
    ['/metrics', ['marketer'], false],
    ['/library', ['marketer'], true],
    ['/outbox', [], true],
    // Item pages decide for themselves (a marketer opens their own items); the page shows a 403 or 404.
    ['/items/40', ['marketer'], true],
    ['/', ['marketer'], true],
  ])('%s for %j: %s', (pathname, roles, expected) => {
    expect(canOpen(pathname, roles)).toBe(expected);
  });
});

describe('afterSignIn', () => {
  it('sends a fresh sign-in at / to the landing', () => {
    expect(afterSignIn({ pathname: '/', roles: ['marketer'], userChanged: false })).toBe('/mine');
  });

  it('keeps a deep link the new user can open', () => {
    expect(afterSignIn({ pathname: '/items/40', roles: ['marketer'], userChanged: false })).toBeNull();
  });

  it("replaces a deep link the new user can't open with their landing", () => {
    expect(afterSignIn({ pathname: '/queue', roles: ['marketer'], userChanged: false })).toBe('/mine');
  });

  it("never keeps the previous user's screen in this tab, even one the new user could open", () => {
    expect(afterSignIn({ pathname: '/library', roles: ['admin'], userChanged: true })).toBe('/import');
  });
});
