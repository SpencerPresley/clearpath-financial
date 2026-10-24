/*
 * What a tool call says under the assistant turn that made it: the tool in plain words, with tense carrying
 * the status ("Searching items" -> "Searched items"), plus the items it touched as links. Tool names are the
 * backend's (backend/assistant/tools.py); an unknown name falls back to the name in words.
 */

import type { IconKey } from '../../ui/icons';

export type ChipStatus = 'running' | 'finished' | 'error' | 'awaiting' | 'stopped';
export type EmailOutcome = 'sent' | 'declined' | 'blocked';

export interface ToolChip {
  id: string;
  name: string;
  status: ChipStatus;
  label: string;
  itemKeys: string[];
  /** error = failed or blocked; everything else reads neutral (finished, your own choices). */
  tone: 'neutral' | 'error';
  /** A glyph that says what happened, when the status glyph doesn't (email outcomes). */
  icon?: IconKey;
  /** send_email only: what became of the draft, from the tool's artifact. */
  outcome?: EmailOutcome;
  /** sent: the Outbox row. */
  outboxId?: number;
}

interface Phrases {
  running: string;
  finished: string;
  error: string;
}

const ITEM_KEY = /^CP-\d+$/;

function phrases(name: string, key: string | undefined): Phrases {
  switch (name) {
    case 'search_items':
      return { running: 'Searching items', finished: 'Searched items', error: "Couldn't search items" };
    case 'get_item': {
      const what = key ?? 'an item';
      return { running: `Reading ${what}`, finished: `Read ${what}`, error: `Couldn't read ${what}` };
    }
    case 'search_precedents':
      return {
        running: 'Searching precedents',
        finished: 'Searched precedents',
        error: "Couldn't search precedents",
      };
    case 'get_queue_stats':
      return {
        running: 'Checking queue stats',
        finished: 'Checked queue stats',
        error: "Couldn't check queue stats",
      };
    case 'get_offer_terms':
      return {
        running: 'Checking offer terms',
        finished: 'Checked offer terms',
        error: "Couldn't check offer terms",
      };
    case 'get_partner':
      return {
        running: 'Looking up a partner',
        finished: 'Looked up a partner',
        error: "Couldn't look up the partner",
      };
    case 'build_export':
      return {
        running: 'Building an export',
        finished: 'Built an export',
        error: "Couldn't build the export",
      };
    case 'send_email':
      return { running: 'Drafting an email', finished: 'Sent an email', error: 'Email not sent' };
    default: {
      const words = name.replace(/_/g, ' ');
      const sentence = words.charAt(0).toUpperCase() + words.slice(1);
      return { running: sentence, finished: sentence, error: `${sentence} failed` };
    }
  }
}

export function chipLabel(name: string, status: ChipStatus, key?: string): string {
  const p = phrases(name, key);
  switch (status) {
    case 'running':
      return p.running;
    case 'finished':
      return p.finished;
    case 'error':
      return p.error;
    case 'awaiting':
      return name === 'send_email' ? 'Email waiting for your approval' : `${p.running}, waiting for you`;
    case 'stopped':
      return `${p.running}, stopped`;
  }
}

function asItemKey(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isInteger(value)) return `CP-${String(value)}`;
  if (typeof value === 'string' && ITEM_KEY.test(value.trim().toUpperCase()))
    return value.trim().toUpperCase();
  return undefined;
}

/** Item keys a call touched: the tool result's `artifact.item_keys`, else an item named in the args. */
export function itemKeysOf(args: unknown, artifact: unknown): string[] {
  const keys: string[] = [];
  const fromArtifact = (artifact as { item_keys?: unknown } | null | undefined)?.item_keys;
  if (Array.isArray(fromArtifact)) {
    for (const value of fromArtifact as unknown[]) {
      const key = asItemKey(value);
      if (key !== undefined) keys.push(key);
    }
  }
  if (keys.length === 0 && typeof args === 'object' && args !== null) {
    const record = args as Record<string, unknown>;
    for (const field of ['item_key', 'key', 'item_id', 'item']) {
      const key = asItemKey(record[field]);
      if (key !== undefined) {
        keys.push(key);
        break;
      }
    }
  }
  return [...new Set(keys)];
}

export interface CallInput {
  id: string;
  name: string;
  args: unknown;
}

export interface CallResult {
  status: 'success' | 'error';
  artifact: unknown;
}

export interface ChipContext {
  /** Tool messages by tool_call_id. */
  results: ReadonlyMap<string, CallResult>;
  /** Live status from the stream's tool events, by call id. */
  live: ReadonlyMap<string, 'running' | 'finished' | 'error'>;
  /** tool_call_id of the call paused on approval, if any. */
  awaitingCallId: string | undefined;
  isLoading: boolean;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? (value as unknown[]).filter((v): v is string => typeof v === 'string') : [];
}

/**
 * The email outcome from send_email's artifact (backend/assistant/schemas.py), written by the app, not the
 * model: after an injection the model's own words are the thing we can't trust.
 */
function emailOutcome(
  artifact: unknown,
): Pick<ToolChip, 'outcome' | 'label' | 'tone' | 'icon' | 'outboxId'> | null {
  if (typeof artifact !== 'object' || artifact === null) return null;
  const record = artifact as Record<string, unknown>;
  const to = strings(record.to);
  switch (record.outcome) {
    case 'sent':
      return {
        outcome: 'sent',
        tone: 'neutral',
        icon: 'nav.outbox',
        label: `Sent to ${to.join(', ')} · approved by you`,
        outboxId: typeof record.outbox_id === 'number' ? record.outbox_id : undefined,
      };
    case 'declined':
      return { outcome: 'declined', tone: 'neutral', icon: 'action.close', label: 'You declined this email' };
    case 'blocked': {
      const refused = strings(record.refused);
      const reason = typeof record.reason === 'string' ? record.reason : '';
      let label: string;
      if (refused.length === 1) label = `Blocked: ${refused.join('')} isn't an internal address`;
      else if (refused.length > 1) label = `Blocked: ${refused.join(', ')} aren't internal addresses`;
      else label = `Blocked: ${reason === '' ? 'not sent' : reason}`;
      return { outcome: 'blocked', tone: 'error', icon: 'feedback.error', label };
    }
    default:
      return null;
  }
}

export function chipFor(call: CallInput, context: ChipContext): ToolChip {
  const result = context.results.get(call.id);
  let status: ChipStatus;
  if (result !== undefined) status = result.status === 'error' ? 'error' : 'finished';
  else if (call.id === context.awaitingCallId) status = 'awaiting';
  else status = context.live.get(call.id) ?? (context.isLoading ? 'running' : 'stopped');
  const itemKeys = itemKeysOf(call.args, result?.artifact);
  const argKey = itemKeysOf(call.args, undefined)[0];
  const base: ToolChip = {
    id: call.id,
    name: call.name,
    status,
    label: chipLabel(call.name, status, argKey),
    itemKeys,
    tone: status === 'error' ? 'error' : 'neutral',
  };
  const outcome = call.name === 'send_email' && result !== undefined ? emailOutcome(result.artifact) : null;
  return outcome === null ? base : { ...base, ...outcome };
}
