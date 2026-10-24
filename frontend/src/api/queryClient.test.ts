import { describe, expect, it } from 'vitest';

import { ApiError } from './mutator';
import { createQueryClient, shouldRetry } from './queryClient';

describe('shouldRetry', () => {
  it.each([400, 401, 403, 404, 409, 422, 429])(
    'never retries a %i: asking again gets the same answer',
    (status) => {
      expect(shouldRetry(0, new ApiError(status, {}))).toBe(false);
    },
  );

  it.each([500, 502, 503])('retries a %i up to three times', (status) => {
    const error = new ApiError(status, {});
    expect([0, 1, 2, 3].map((n) => shouldRetry(n, error))).toEqual([true, true, true, false]);
  });

  it('retries a network failure (fetch rejects with TypeError) up to three times', () => {
    const error = new TypeError('Failed to fetch');
    expect([0, 2, 3].map((n) => shouldRetry(n, error))).toEqual([true, true, false]);
  });

  it('is the default for every query', () => {
    expect(createQueryClient().getDefaultOptions().queries?.retry).toBe(shouldRetry);
  });
});
