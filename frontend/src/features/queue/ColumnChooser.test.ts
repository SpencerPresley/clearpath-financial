import { afterEach, describe, expect, it } from 'vitest';

import { COLUMNS_KEY, readColumns } from './ColumnChooser';

describe('readColumns', () => {
  afterEach(() => {
    window.localStorage.removeItem(COLUMNS_KEY);
  });

  it('keeps a column added after the choice was stored at its default (hidden)', () => {
    window.localStorage.setItem(COLUMNS_KEY, JSON.stringify({ tags: true, partner: false }));
    const columns = readColumns();
    expect(columns).toMatchObject({ tags: true, partner: false, notes: false });
  });
});
