import { describe, expect, it } from 'vitest';

import { chipFor, chipLabel, itemKeysOf } from './toolChips';
import type { ChipContext } from './toolChips';

const idle: ChipContext = {
  results: new Map(),
  live: new Map(),
  awaitingCallId: undefined,
  isLoading: false,
};

describe('chipLabel', () => {
  it('names tools in plain words, with the tense carrying the status', () => {
    expect(chipLabel('search_items', 'running')).toBe('Searching items');
    expect(chipLabel('search_items', 'finished')).toBe('Searched items');
    expect(chipLabel('get_item', 'finished', 'CP-1042')).toBe('Read CP-1042');
    expect(chipLabel('get_offer_terms', 'finished')).toBe('Checked offer terms');
    expect(chipLabel('send_email', 'awaiting')).toBe('Email waiting for your approval');
    expect(chipLabel('send_email', 'error')).toBe('Email not sent');
    expect(chipLabel('lookup_widget', 'finished')).toBe('Lookup widget');
  });
});

describe('itemKeysOf', () => {
  it('prefers the result artifact, falls back to an item in the args', () => {
    expect(itemKeysOf({ q: 'loan' }, { item_keys: ['CP-1', 'CP-2', 'CP-1', 'junk'] })).toEqual([
      'CP-1',
      'CP-2',
    ]);
    expect(itemKeysOf({ item_key: 'cp-1042' }, null)).toEqual(['CP-1042']);
    expect(itemKeysOf({ item_id: 7 }, undefined)).toEqual(['CP-7']);
    expect(itemKeysOf({ q: 'CP-1 loan' }, null)).toEqual([]);
  });
});

describe('chipFor', () => {
  const call = { id: 'c1', name: 'get_item', args: { item_key: 'CP-9' } };

  it('is finished or failed once its tool message exists', () => {
    const results = new Map([['c1', { status: 'success' as const, artifact: { item_keys: ['CP-9'] } }]]);
    expect(chipFor(call, { ...idle, results })).toMatchObject({
      status: 'finished',
      label: 'Read CP-9',
      itemKeys: ['CP-9'],
    });
    const failed = new Map([['c1', { status: 'error' as const, artifact: null }]]);
    expect(chipFor(call, { ...idle, results: failed }).label).toBe("Couldn't read CP-9");
  });

  it('waits on approval, runs while the stream is live, and says stopped when the run ended without a result', () => {
    expect(chipFor(call, { ...idle, awaitingCallId: 'c1' }).status).toBe('awaiting');
    expect(chipFor(call, { ...idle, isLoading: true }).status).toBe('running');
    expect(chipFor(call, { ...idle, live: new Map([['c1', 'finished' as const]]) }).status).toBe('finished');
    expect(chipFor(call, idle)).toMatchObject({ status: 'stopped', label: 'Reading CP-9, stopped' });
  });
});

describe('send_email outcomes (app text from the tool artifact, never the model)', () => {
  const call = { id: 'c2', name: 'send_email', args: { to: ['a@clearpath.demo'] } };
  const result = (artifact: unknown, status: 'success' | 'error' = 'success') => ({
    ...idle,
    results: new Map([['c2', { status, artifact }]]),
  });

  it('sent: who it went to, that you approved it, and where it is', () => {
    expect(
      chipFor(
        call,
        result({
          outcome: 'sent',
          outbox_id: 12,
          to: ['a@clearpath.demo', 'b@clearpath.demo'],
          item_keys: [],
        }),
      ),
    ).toMatchObject({
      outcome: 'sent',
      tone: 'neutral',
      icon: 'nav.outbox',
      label: 'Sent to a@clearpath.demo, b@clearpath.demo · approved by you',
      outboxId: 12,
    });
  });

  it('declined: your choice, neutral', () => {
    expect(
      chipFor(call, result({ outcome: 'declined', to: ['a@clearpath.demo'], item_keys: [] }, 'error')),
    ).toMatchObject({
      outcome: 'declined',
      tone: 'neutral',
      icon: 'action.close',
      label: 'You declined this email',
    });
  });

  it('blocked: names the refused addresses in error tone, or gives the reason', () => {
    expect(
      chipFor(
        call,
        result(
          {
            outcome: 'blocked',
            refused: ['marketing@lendfast.example'],
            reason: 'Not an internal address',
            to: ['marketing@lendfast.example'],
            item_keys: [],
          },
          'error',
        ),
      ),
    ).toMatchObject({
      outcome: 'blocked',
      tone: 'error',
      icon: 'feedback.error',
      label: "Blocked: marketing@lendfast.example isn't an internal address",
    });
    expect(
      chipFor(
        call,
        result(
          { outcome: 'blocked', refused: ['x@a.example', 'y@b.example'], reason: '', to: [], item_keys: [] },
          'error',
        ),
      ).label,
    ).toBe("Blocked: x@a.example, y@b.example aren't internal addresses");
    expect(
      chipFor(
        call,
        result(
          { outcome: 'blocked', refused: [], reason: 'Too many recipients.', to: [], item_keys: [] },
          'error',
        ),
      ).label,
    ).toBe('Blocked: Too many recipients.');
  });

  it('falls back to the plain label without an artifact', () => {
    expect(chipFor(call, result(null, 'error'))).toMatchObject({ label: 'Email not sent', tone: 'error' });
  });
});
