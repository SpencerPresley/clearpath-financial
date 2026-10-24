/*
 * The adapter `useStream` talks to (docs/plan/assistant.md, spike findings 1-5). It maps the protocol's
 * thread-centric commands onto our two request-scoped streaming endpoints:
 *
 *   run.start     -> POST /api/assistant/threads/{id}/runs                  (SSE)
 *   input.respond -> POST /api/assistant/threads/{id}/interrupts/{iid}      (SSE)
 *
 * The run lives inside that one response, so the adapter plays the "server" the controller expects: it
 * numbers events (`seq` monotonic per thread across runs, since the loading tracker drops a `running` whose seq
 * isn't above the last terminal), keeps the current run's events in a replay buffer for subscriptions opened
 * late (the controller opens its root stream only after `run.start` resolves), and filters per subscription.
 *
 * `send` resolves once response headers arrive, so pre-stream failures (404/409/422) reject the submit or
 * respond with an ApiError carrying the JSON body; the SSE body is pumped in the background.
 */
import type { AgentServerAdapter } from '@langchain/react';

import {
  getGetAssistantThreadStateUrl,
  getRespondToAssistantInterruptUrl,
  getStartAssistantRunUrl,
} from '../../api/generated/assistant/assistant';
import type { AssistantRunIn, AssistantThreadStateOut } from '../../api/generated/model';
import { ApiError, customFetch, streamFetch } from '../../api/mutator';
import { readSse } from './sse';
import type { AssistantConfigurable } from './types';

type Command = Parameters<AgentServerAdapter['send']>[0];
type SendResult = Awaited<ReturnType<AgentServerAdapter['send']>>;
type SubscribeParams = Parameters<NonNullable<AgentServerAdapter['openEventStream']>>[0];
type EventStreamHandle = ReturnType<NonNullable<AgentServerAdapter['openEventStream']>>;
type StreamMessage = EventStreamHandle['events'] extends AsyncIterable<infer M> ? M : never;
type ProtocolEvent = Extract<StreamMessage, { type: 'event' }>;

/** One line for a stream that dropped or ended without saying how the run finished. */
export const LOST_STREAM = 'Lost the connection to the assistant. Reload the thread and try again.';

class EventQueue {
  #items: StreamMessage[] = [];
  #waiters: ((result: IteratorResult<StreamMessage>) => void)[] = [];
  #closed = false;

  push(item: StreamMessage) {
    if (this.#closed) return;
    const waiter = this.#waiters.shift();
    if (waiter === undefined) this.#items.push(item);
    else waiter({ value: item, done: false });
  }

  close() {
    this.#closed = true;
    this.#items = [];
    for (const waiter of this.#waiters.splice(0)) waiter({ value: undefined, done: true });
  }

  iterable(onReturn: () => void): AsyncIterable<StreamMessage> {
    return {
      [Symbol.asyncIterator]: () => ({
        next: () => {
          const item = this.#items.shift();
          if (item !== undefined) return Promise.resolve({ value: item, done: false });
          if (this.#closed) return Promise.resolve({ value: undefined, done: true });
          return new Promise((resolve) => this.#waiters.push(resolve));
        },
        return: () => {
          onReturn();
          return Promise.resolve({ value: undefined, done: true });
        },
      }),
    };
  }
}

interface Subscriber {
  params: SubscribeParams;
  queue: EventQueue;
}

function channelOf(method: string): string {
  return method === 'input.requested' ? 'input' : method;
}

function matches(event: ProtocolEvent, params: SubscribeParams): boolean {
  if (!(params.channels as string[]).includes(channelOf(event.method))) return false;
  const namespace = event.params.namespace;
  const prefixes = params.namespaces ?? [];
  if (prefixes.length === 0) {
    return params.depth === undefined || namespace.length <= params.depth;
  }
  return prefixes.some(
    (prefix) =>
      prefix.every((part, index) => namespace[index] === part) &&
      (params.depth === undefined || namespace.length - prefix.length <= params.depth),
  );
}

function isProtocolEvent(value: unknown): value is ProtocolEvent {
  if (typeof value !== 'object' || value === null) return false;
  const event = value as { type?: unknown; method?: unknown; params?: { namespace?: unknown } };
  return event.type === 'event' && typeof event.method === 'string' && Array.isArray(event.params?.namespace);
}

function isTerminal(event: ProtocolEvent): boolean {
  if (event.method !== 'lifecycle' || event.params.namespace.length > 0) return false;
  const lifecycle = (event.params as { data?: { event?: unknown } }).data?.event;
  return lifecycle === 'completed' || lifecycle === 'interrupted' || lifecycle === 'failed';
}

function textOf(content: unknown): string {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content
    .map((block: unknown) =>
      typeof block === 'object' && block !== null && 'text' in block && typeof block.text === 'string'
        ? block.text
        : '',
    )
    .join('');
}

/** The newest human message in the run.start input (the controller sends only the new one). */
function lastHumanMessage(input: unknown): { id: string; content: string } | undefined {
  const messages = (input as { messages?: unknown } | null)?.messages;
  if (!Array.isArray(messages)) return undefined;
  for (const message of ([...(messages as unknown[])] as unknown[]).reverse()) {
    if (typeof message !== 'object' || message === null) continue;
    const { type, role, id, content } = message as Record<string, unknown>;
    if (type === 'human' || role === 'user' || role === 'human') {
      return { id: typeof id === 'string' && id !== '' ? id : crypto.randomUUID(), content: textOf(content) };
    }
  }
  return undefined;
}

export class AssistantTransport implements AgentServerAdapter {
  /**
   * Read by useStream to build its fallback SDK Client (resolveClientApiUrl). The controller calls
   * `client.threads.getHistory` directly on hydrate, bypassing this adapter; without a URL that's a POST to
   * http://localhost:8123. Here it stays same-origin under our owner-checked thread routes
   * (POST /api/assistant/threads/{id}/history), and the controller ignores its failure.
   */
  readonly apiUrl = `${window.location.origin}/api/assistant`;
  #threadId: string;
  #seq = 0;
  #buffer: ProtocolEvent[] = [];
  #subscribers = new Set<Subscriber>();
  #run: AbortController | null = null;
  #requests = new Set<AbortController>();

  constructor({ threadId }: { threadId: string }) {
    this.#threadId = threadId;
  }

  get threadId(): string {
    return this.#threadId;
  }

  /** Events held for replay from the current run (tests). */
  get bufferedCount(): number {
    return this.#buffer.length;
  }

  setThreadId(threadId: string): void {
    if (threadId === this.#threadId) return;
    this.abortRun();
    this.#threadId = threadId;
    this.#seq = 0;
    this.#buffer = [];
  }

  open(): Promise<void> {
    return Promise.resolve();
  }

  async send(command: Command): Promise<SendResult> {
    if (command.method === 'run.start') {
      const message = lastHumanMessage(command.params.input);
      if (message === undefined) {
        return { type: 'error', id: command.id, error: 'invalid_argument', message: 'No message to send.' };
      }
      const configurable = command.params.config?.configurable as AssistantConfigurable | undefined;
      const itemId = configurable?.item_id;
      const body: AssistantRunIn = { message, ...(typeof itemId === 'number' ? { item_id: itemId } : {}) };
      return this.#startRun(command.id, getStartAssistantRunUrl(this.#threadId), body);
    }
    if (command.method === 'input.respond') {
      const params = command.params;
      const one =
        'responses' in params ? (params.responses.length === 1 ? params.responses[0] : undefined) : params;
      if (one === undefined) {
        return {
          type: 'error',
          id: command.id,
          error: 'not_supported',
          message: 'Respond to one approval at a time.',
        };
      }
      const url = getRespondToAssistantInterruptUrl(this.#threadId, one.interrupt_id);
      return this.#startRun(command.id, url, one.response);
    }
    return {
      type: 'error',
      id: command.id,
      error: 'not_supported',
      message: `${command.method} isn't supported by the assistant.`,
    };
  }

  async #startRun(id: number, url: string, body: unknown): Promise<SendResult> {
    this.abortRun();
    const run = new AbortController();
    this.#run = run;
    const response = await streamFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal: run.signal,
    });
    const appliedThrough = this.#seq;
    this.#buffer = [];
    if (response.body !== null) void this.#pump(response.body, run, this.#threadId);
    return {
      type: 'success',
      id,
      result: { run_id: `${this.#threadId}:${String(appliedThrough)}` },
      meta: { applied_through_seq: appliedThrough },
    };
  }

  async #pump(body: ReadableStream<Uint8Array>, run: AbortController, threadId: string): Promise<void> {
    let ended = false;
    try {
      for await (const data of readSse(body, run.signal)) {
        if (run.signal.aborted) return;
        if (!isProtocolEvent(data)) continue;
        this.#emit(data);
        if (isTerminal(data)) ended = true;
      }
    } catch {
      // A dropped connection mid-run (not a user stop): reported below as a failed run.
    } finally {
      if (this.#run === run) this.#run = null;
    }
    if (!ended && !run.signal.aborted && threadId === this.#threadId) {
      this.#emit({
        type: 'event',
        method: 'lifecycle',
        params: { namespace: [], timestamp: Date.now(), data: { event: 'failed', error: LOST_STREAM } },
      });
    }
  }

  #emit(raw: ProtocolEvent) {
    this.#seq += 1;
    const event = { ...raw, seq: this.#seq, event_id: `${this.#threadId}:${String(this.#seq)}` };
    this.#buffer.push(event);
    for (const subscriber of this.#subscribers) {
      if (matches(event, subscriber.params)) subscriber.queue.push(event);
    }
  }

  /** Cancel the run in flight: closing the stream is what cancels it server-side. */
  abortRun(): void {
    this.#run?.abort();
    this.#run = null;
  }

  events(): AsyncIterable<StreamMessage> {
    // Everything arrives through openEventStream; this WebSocket-style channel never yields.
    return {
      [Symbol.asyncIterator]: () => ({
        next: () => new Promise<IteratorResult<StreamMessage>>(() => undefined),
      }),
    };
  }

  openEventStream(params: SubscribeParams): EventStreamHandle {
    const subscriber: Subscriber = { params, queue: new EventQueue() };
    for (const event of this.#buffer) {
      if (matches(event, params)) subscriber.queue.push(event);
    }
    this.#subscribers.add(subscriber);
    const close = () => {
      this.#subscribers.delete(subscriber);
      subscriber.queue.close();
    };
    return { events: subscriber.queue.iterable(close), ready: Promise.resolve(), close };
  }

  // The adapter interface declares getState generic over the caller's state type; ours is fixed by the API.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
  async getState<StateType = unknown>(): Promise<{ values: StateType } | null> {
    if (this.#threadId === '') return null;
    const request = new AbortController();
    this.#requests.add(request);
    try {
      const state = await customFetch<AssistantThreadStateOut>(
        getGetAssistantThreadStateUrl(this.#threadId),
        {
          signal: request.signal,
        },
      );
      // Runs live inside their request, so a hydrate never has a stream to join. A checkpoint with `next` set
      // and no pending approval is a run cut short (Stop, closed tab, dropped connection) or another tab's run
      // we can't observe; reported as-is, the controller would show it as loading with nothing to end it. Only
      // an approval keeps the thread active; a real concurrent run answers the next send with a 409.
      const paused = state.tasks.some((task) => task.interrupts.length > 0);
      const normalized = paused ? state : { ...state, next: [] };
      return normalized as unknown as { values: StateType };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null; // not yours, or gone
      throw error;
    } finally {
      this.#requests.delete(request);
    }
  }

  getHistory(): Promise<never[]> {
    return Promise.resolve([]);
  }

  close(): Promise<void> {
    this.abortRun();
    for (const request of this.#requests) request.abort();
    this.#requests.clear();
    return Promise.resolve();
  }
}
