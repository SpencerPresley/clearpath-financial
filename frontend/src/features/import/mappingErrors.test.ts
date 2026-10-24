import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/mutator';
import { mappingErrors } from './mappingErrors';

function invalid(fields: { loc: (string | number)[]; message: string }[], message = 'Fix the mapping.') {
  return new ApiError(422, { code: 'invalid_input', message, details: {}, fields });
}

describe('mappingErrors', () => {
  it('puts an indexed issue on the row that was sent at that index', () => {
    const errors = mappingErrors(
      invalid([{ loc: ['body', 'value_mappings', 1, 'value'], message: "'Acme' isn't a valid Partner." }]),
    );
    expect(errors.value_mappings).toEqual({ 1: "'Acme' isn't a valid Partner." });
    expect(errors.form).toBeNull();
  });

  it('keeps list-level issues (two columns on one field) as one line for the step', () => {
    const errors = mappingErrors(
      invalid([
        {
          loc: ['body', 'columns'],
          message: "Title is mapped from both 'Asset' and 'Name'; set one to Ignore.",
        },
      ]),
    );
    expect(errors.columns).toEqual({});
    expect(errors.form).toBe("Title is mapped from both 'Asset' and 'Name'; set one to Ignore.");
  });

  it("uses the server's one-line message for a 409", () => {
    const errors = mappingErrors(
      new ApiError(409, { code: 'conflict', message: "This import is committed; its mapping can't change." }),
    );
    expect(errors.form).toBe("This import is committed; its mapping can't change.");
  });
});
