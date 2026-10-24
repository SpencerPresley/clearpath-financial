import { describe, expect, it } from 'vitest';

import { fieldErrorText } from './formErrors';

describe('fieldErrorText', () => {
  it('reads schema issues and plain strings, first non-empty wins', () => {
    expect(fieldErrorText([])).toBeUndefined();
    expect(fieldErrorText([undefined, { message: 'Enter a title.' }])).toBe('Enter a title.');
    expect(fieldErrorText(['', 'Taken.'])).toBe('Taken.');
  });
});
