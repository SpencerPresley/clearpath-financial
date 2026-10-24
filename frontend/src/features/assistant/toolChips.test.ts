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
