import { describe, expect, it } from 'vitest';

import { NotificationKind } from '../../api/generated/model';
import type { NotificationOut } from '../../api/generated/model';
import { DANA, SAM, notificationFixture } from '../../test/fixtures/notifications';
import { KIND_ICONS, describeNotification, notificationLink } from './text';

const text = (overrides: Parameters<typeof notificationFixture>[0]) =>
  describeNotification(notificationFixture(overrides)).text;

describe('describeNotification', () => {
  it('phrases decisions as who did what to which item', () => {
    expect(text({})).toBe('Dana Reyes requested changes on CP-42 · Fall personal loan promo');
    expect(text({ detail: { kind: 'decision', outcome: 'approved' } })).toBe(
      'Dana Reyes approved CP-42 · Fall personal loan promo',
    );
    expect(text({ detail: { kind: 'decision', outcome: 'approved_with_edits' } })).toBe(
      'Dana Reyes approved CP-42 · Fall personal loan promo with edits',
    );
    expect(text({ detail: { kind: 'decision', outcome: 'rejected' } })).toBe(
      'Dana Reyes rejected CP-42 · Fall personal loan promo',
    );
  });

  it('keeps the outcome after the item, where the title can truncate without hiding it', () => {
    const parts = describeNotification(
      notificationFixture({ detail: { kind: 'decision', outcome: 'approved_with_edits' } }),
    );
    expect(parts.before).toBe('Dana Reyes approved ');
    expect(parts.item).toEqual({ key: 'CP-42', title: 'Fall personal loan promo' });
    expect(parts.after).toBe(' with edits');
  });

  it('phrases each assignment mode', () => {
    const assigned = (mode: 'manual' | 'handoff' | 'lowest_load' | 'sticky' | 'pool', actor = SAM) =>
      text({ kind: 'assignment', actor, detail: { kind: 'assignment', mode } });
    expect(assigned('manual')).toBe('Sam Okafor assigned CP-42 · Fall personal loan promo to you');
    expect(assigned('handoff')).toBe('Sam Okafor handed CP-42 · Fall personal loan promo to you');
    // Auto-assignment on submit: the submitter didn't choose the reviewer, so no actor is named.
    expect(assigned('lowest_load')).toBe('CP-42 · Fall personal loan promo was assigned to you');
    expect(assigned('sticky')).toBe('CP-42 · Fall personal loan promo is back for your review');
    expect(assigned('pool')).toBe('CP-42 · Fall personal loan promo is in the unassigned pool');
  });

  it('phrases mentions, re-reviews and expiry warnings', () => {
    expect(
      text({ kind: 'mention', actor: SAM, detail: { kind: 'mention', comment_id: 1, version_n: 2 } }),
    ).toBe('Sam Okafor mentioned you on CP-42 · Fall personal loan promo');
    expect(
      text({ kind: 'rereview', actor: null, detail: { kind: 'rereview', reason: 'terms_changed' } }),
    ).toBe('CP-42 · Fall personal loan promo needs re-review · offer terms changed');
    expect(
      text({
        kind: 'expiry_warning',
        actor: null,
        detail: { kind: 'expiry_warning', expires_at: '2026-11-23T12:00:00Z' },
      }),
    ).toBe('Approval for CP-42 · Fall personal loan promo expires Nov 23');
  });

  it('phrases blocking findings on a partner page, with the count when the event has it', () => {
    const page = (detail: NotificationOut['detail']) => text({ kind: 'page_findings', actor: null, detail });
    // The item leads, so its title is what truncates last; the finding count follows it.
    expect(page({ kind: 'page_findings', new_blocking_count: 2 })).toBe(
      'CP-42 · Fall personal loan promo · 2 new blocking findings on the partner page',
    );
    expect(page({ kind: 'page_findings', new_blocking_count: 1 })).toBe(
      'CP-42 · Fall personal loan promo · 1 new blocking finding on the partner page',
    );
    expect(page(null)).toBe('CP-42 · Fall personal loan promo · new blocking findings on the partner page');
  });

  it('falls back to the stored message when the row has no event detail or no item', () => {
    expect(text({ detail: null, message: 'CP-42 Fall promo: approved' })).toBe('CP-42 Fall promo: approved');
    expect(text({ item_id: null, item_key: null, item_title: null, message: 'Stored' })).toBe('Stored');
    expect(text({ kind: 'mention', actor: null, detail: null })).toBe(
      'You were mentioned on CP-42 · Fall personal loan promo',
    );
  });

  it('names a decision without an actor by its outcome', () => {
    expect(text({ actor: null })).toBe('Changes requested on CP-42 · Fall personal loan promo');
  });

  it('picks the icon from the outcome for decisions, and from the kind otherwise', () => {
    expect(describeNotification(notificationFixture({})).icon).toBe('status.changes_requested');
    expect(
      describeNotification(notificationFixture({ detail: { kind: 'decision', outcome: 'approved' } })).icon,
    ).toBe('status.approved');
    expect(describeNotification(notificationFixture({ kind: 'mention', detail: null })).icon).toBe(
      'notify.mention',
    );
  });

  it('shows the pool, not the assign glyph, when an item lands in the unassigned pool', () => {
    const assigned = (mode: 'pool' | 'manual') =>
      describeNotification(notificationFixture({ kind: 'assignment', detail: { kind: 'assignment', mode } }))
        .icon;
    expect(assigned('pool')).toBe('nav.queue');
    expect(assigned('manual')).toBe('action.assign');
  });

  it('tones drift findings as alert, like the placement on the item page', () => {
    expect(describeNotification(notificationFixture({ kind: 'page_findings', detail: null })).tone).toBe(
      'alert',
    );
  });

  it('gives each kind its own glyph', () => {
    const glyphs = Object.values(NotificationKind).map((kind) => KIND_ICONS[kind]);
    expect(new Set(glyphs).size).toBe(glyphs.length);
  });
});

describe('notificationLink', () => {
  it('opens the item, on the comment and its version for mentions', () => {
    expect(notificationLink(notificationFixture({}))).toEqual({ itemId: '42', search: {} });
    expect(
      notificationLink(
        notificationFixture({ kind: 'mention', detail: { kind: 'mention', comment_id: 1, version_n: 2 } }),
      ),
    ).toEqual({ itemId: '42', search: { tab: 'comments', v: 2, comment: 1 } });
    expect(notificationLink(notificationFixture({ kind: 'mention', actor: DANA, detail: null }))).toEqual({
      itemId: '42',
      search: { tab: 'comments' },
    });
  });

  it('opens Details, where the placement is flagged, for page findings', () => {
    expect(notificationLink(notificationFixture({ kind: 'page_findings', detail: null }))).toEqual({
      itemId: '42',
      search: { tab: 'details' },
    });
  });

  it('has nowhere to go without an item', () => {
    expect(notificationLink(notificationFixture({ item_id: null }))).toBeNull();
  });
});
