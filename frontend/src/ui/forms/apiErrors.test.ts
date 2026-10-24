import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/mutator';
import { apiErrorBody, apiErrorMessage, fieldErrorsFrom } from './apiErrors';

const FIELDS = ['title', 'partner_id', 'planned_first_run'] as const;

describe('fieldErrorsFrom', () => {
  it('maps ninja validation locs and domain field issues onto fields', () => {
    const error = new ApiError(422, {
      code: 'validation_error',
      message: 'Invalid input',
      fields: [
        {
          loc: ['body', 'payload', 'title'],
          message: 'String should have at most 300 characters',
          type: 'x',
        },
        { loc: ['partner_id'], message: 'A partner is required for affiliate pages.', type: 'invalid' },
        { loc: ['body', 'payload', 'markets', 0], message: 'Unknown market', type: 'enum' },
      ],
    });
    expect(fieldErrorsFrom(error, FIELDS)).toEqual({
      fields: {
        title: 'String should have at most 300 characters',
        partner_id: 'A partner is required for affiliate pages.',
      },
      form: 'Unknown market',
    });
  });

  it('puts a non-field error on the form', () => {
    const error = new ApiError(409, { code: 'conflict', message: 'Item changed. Reload and try again.' });
    expect(fieldErrorsFrom(error, FIELDS)).toEqual({
      fields: {},
      form: 'Item changed. Reload and try again.',
    });
  });

  it('falls back to a generic line for non-API errors', () => {
    expect(fieldErrorsFrom(new TypeError('Failed to fetch'), FIELDS).form).toBe(
      "Couldn't reach the server. Check your connection and try again.",
    );
  });
});

describe('apiErrorBody', () => {
  it('reads ErrorOut from an ApiError and ignores other bodies', () => {
    expect(apiErrorBody(new ApiError(409, { code: 'ai_check_pending', message: 'm' }))?.code).toBe(
      'ai_check_pending',
    );
    expect(apiErrorBody(new ApiError(502, '<html>'))).toBeUndefined();
    expect(apiErrorMessage(new ApiError(502, '<html>'))).toBe(
      'The server had a problem. Try again in a minute.',
    );
  });
});
