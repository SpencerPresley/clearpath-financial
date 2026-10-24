/*
 * UI-review screenshots of the quick-jump box and a linked comment (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots-search.spec.ts
 * Output: docs/plan/reviews/ui/search/<state>-1440.png.
 */
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { NOW } from '../src/test/fixtures/review';
import { MENTION_COMMENT, stubNotifications } from './notificationsApi.ts';
import { stubSearch } from './searchApi.ts';
import type { SearchMode } from './searchApi.ts';
import { stubApi } from './stubApi.ts';

const OUT = '../docs/plan/reviews/ui/search';

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');
test.use({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });

const shots: { name: string; type: string; mode?: SearchMode; ready: (page: Page) => Promise<void> }[] = [
  {
    name: 'idle',
    type: '',
    ready: (page) => expect(page.getByRole('combobox', { name: 'Jump to item' })).toBeVisible(),
  },
  {
    name: 'focused',
    type: '',
    ready: (page) => expect(page.getByRole('combobox', { name: 'Jump to item' })).toBeFocused(),
  },
  {
    name: 'hint',
    type: 'f',
    ready: (page) => expect(page.getByText('Type a CP key, title words or tracker ID.')).toBeVisible(),
  },
  {
    name: 'results',
    type: 'fall',
    ready: (page) => expect(page.getByRole('option', { name: /CP-1070/ })).toBeVisible(),
  },
  {
    name: 'results-highlighted',
    type: 'fall',
    ready: async (page) => {
      await expect(page.getByRole('option', { name: /CP-1070/ })).toBeVisible();
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('ArrowDown');
    },
  },
  {
    name: 'legacy',
    type: 'MCR-26',
    ready: (page) => expect(page.getByRole('option', { name: /CP-1188/ })).toBeVisible(),
  },
  {
    name: 'no-match',
    type: 'zzz',
    ready: (page) => expect(page.getByText('No items match “zzz”.')).toBeVisible(),
  },
  {
    name: 'searching',
    type: 'fall',
    mode: 'loading',
    ready: (page) => expect(page.getByText('Searching…')).toBeVisible(),
  },
  {
    name: 'error',
    type: 'fall',
    mode: 'error',
    ready: (page) => expect(page.getByText('Search is temporarily unavailable.')).toBeVisible(),
  },
];

for (const shot of shots) {
  test(`search ${shot.name}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date(NOW));
    await stubApi(page);
    await stubSearch(page, shot.mode);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
    if (shot.name !== 'idle') {
      await page.keyboard.press('ControlOrMeta+k');
      if (shot.type) await page.getByRole('combobox', { name: 'Jump to item' }).pressSequentially(shot.type);
    }
    await shot.ready(page);
    const popover = page.locator('.app-jump');
    if ((await popover.count()) > 0) await expect(popover).toHaveCSS('opacity', '1');
    await page.screenshot({ path: `${OUT}/${shot.name}-1440.png` });
  });
}

test('linked comment', async ({ page }) => {
  await page.clock.setFixedTime(new Date(NOW));
  await stubApi(page);
  await stubNotifications(page, []);
  await page.goto(`/items/1042?tab=comments&v=2&comment=${String(MENTION_COMMENT.id)}`);
  const comment = page.locator(`#comment-${String(MENTION_COMMENT.id)}`);
  await expect(comment).toBeFocused();
  await page.screenshot({ path: `${OUT}/comment-linked-1440.png` });
  await page.waitForTimeout(3_000); // the tint has faded; the bar stays
  await page.screenshot({ path: `${OUT}/comment-linked-after-1440.png` });
});
