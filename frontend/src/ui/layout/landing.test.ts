import { describe, expect, it } from 'vitest';

import type { Role } from '../domain';
import { landingFor } from './landing';

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
