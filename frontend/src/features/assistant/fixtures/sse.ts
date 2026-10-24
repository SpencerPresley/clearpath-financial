/*
 * Test-only builders for assistant SSE bodies and protocol events, shared by the MSW handlers (unit tests)
 * and the Playwright stub (e2e). Frames match the server's: `event: <method>\ndata: <json>\n\n`.
 */
import type { WireEvent } from './wire';

export const KEEPALIVE = ': keepalive\n\n';

export function sseText(events: readonly WireEvent[], { keepalive = false } = {}): string {
  const frames = events.map((event) => `event: ${event.method}\ndata: ${JSON.stringify(event)}\n\n`);
  return (keepalive ? KEEPALIVE : '') + frames.join(keepalive ? KEEPALIVE : '');
}

export function lifecycle(
  event: 'running' | 'completed' | 'interrupted' | 'failed',
  error?: string,
): WireEvent {
  return {
    type: 'event',
    method: 'lifecycle',
    params: { namespace: [], data: error === undefined ? { event } : { event, error } },
  };
}

export function values(messages: readonly Record<string, unknown>[]): WireEvent {
  return { type: 'event', method: 'values', params: { namespace: [], data: { messages } } };
}

/** One streamed AI text message: start, one text block of deltas, finish. */
export function aiText(id: string, chunks: readonly string[]): WireEvent[] {
  const event = (data: unknown): WireEvent => ({
    type: 'event',
    method: 'messages',
    params: { namespace: [], node: 'model', data },
  });
  return [
    event({ event: 'message-start', role: 'ai', id }),
    event({ event: 'content-block-start', index: 0, content: { type: 'text', text: '' } }),
    ...chunks.map((text) =>
      event({ event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text } }),
    ),
    event({ event: 'content-block-finish', index: 0, content: { type: 'text', text: chunks.join('') } }),
    event({ event: 'message-finish' }),
  ];
}

/** A run answering whatever message was POSTed (keeping its id, as the checkpoint does) with `text`. */
export function echoRun(text: string, replyId = 'a1') {
  return (body: unknown) => {
    const { message } = body as { message: { id: string; content: string } };
    const run = textRun(message, { id: replyId, text });
    return { events: run.events, state: { ...EMPTY_STATE, values: { messages: run.messages } } };
  };
}

/** A whole run that answers `human` with `reply` and completes. */
export function textRun(
  human: { id: string; content: string },
  reply: { id: string; text: string },
  prior: readonly Record<string, unknown>[] = [],
) {
  const humanMessage = { type: 'human', id: human.id, content: human.content };
  const aiMessage = { type: 'ai', id: reply.id, content: reply.text, tool_calls: [] };
  return {
    events: [
      lifecycle('running'),
      values([...prior, humanMessage]),
      ...aiText(reply.id, reply.text.split(/(?<= )/)),
      values([...prior, humanMessage, aiMessage]),
      lifecycle('completed'),
    ],
    messages: [...prior, humanMessage, aiMessage] as Record<string, unknown>[],
  };
}

export const EMPTY_STATE = {
  values: { messages: [] },
  next: [],
  tasks: [],
  checkpoint: null,
  metadata: null,
  created_at: null,
};
