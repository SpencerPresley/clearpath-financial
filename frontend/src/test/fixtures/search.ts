/*
 * Items the quick-jump box finds, for its unit tests, e2e and screenshots. CP-1042 is review.ts's item (so e2e
 * can open it); CP-1188 is a legacy import that carries its old tracker ID.
 */
import type { ItemRowOut } from '../../api/generated/model';
import { itemRowFixture } from './review';

export const JUMP_ROWS: ItemRowOut[] = [
  itemRowFixture(),
  itemRowFixture({ id: 1061, key: 'CP-1061', title: 'Fall personal loan promo — email', status: 'approved' }),
  itemRowFixture({
    id: 1188,
    key: 'CP-1188',
    title: 'Fall personal loan promo — radio read (2025)',
    status: 'approved',
    is_legacy: true,
    legacy_ref: 'MCR-26-045',
  }),
  itemRowFixture({
    id: 1070,
    key: 'CP-1070',
    title: 'Fall promo landing page, LendRight',
    status: 'changes_requested',
  }),
];

/** What `GET /items?q=` would return for `q`, matching the backend's rule: CP key, title or tracker ID. */
export function jumpResults(q: string, rows: ItemRowOut[] = JUMP_ROWS): ItemRowOut[] {
  const text = q.trim().toLowerCase();
  const key = /^cp-(\d+)$/.exec(text);
  if (key) return rows.filter((row) => row.id === Number(key[1]));
  return rows.filter(
    (row) => row.title.toLowerCase().includes(text) || (row.legacy_ref ?? '').toLowerCase().includes(text),
  );
}
