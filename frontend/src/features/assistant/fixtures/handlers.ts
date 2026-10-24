/*
 * Test-only MSW stand-in for the assistant's run endpoints. Each POST (new run or interrupt response) takes
 * the next scripted run and streams it as SSE, a frame per tick. GET state is stateful: the controller re-reads
 * it after every terminal lifecycle and replaces its messages with it, so it flips to the run's end state
 * before the terminal frame goes out (like the checkpoint the server commits before it says "completed").
 */
import { http, HttpResponse } from 'msw';

import type { AssistantThreadOut } from '../../../api/generated/model';
import { EMPTY_STATE, KEEPALIVE } from './sse';
import type { WireEvent } from './wire';

export interface ScriptedRun {
  events: readonly WireEvent[];
  /** GET state once this run's terminal frame is sent. */
  state: unknown;
  keepalive?: boolean;
  /** Send the whole body at once, before any subscriber can open (as a fast server or e2e would). */
  burst?: boolean;
}

export interface FakeAssistant {
  /** Every POST to a run endpoint, in order. */
  posted: { path: string; body: unknown }[];
  state: unknown;
  /** Thread rows for GET /threads. */
  threads: AssistantThreadOut[];
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 1));

export function sseResponse(run: ScriptedRun, onBeforeTerminal: () => void): HttpResponse<ReadableStream> {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const [index, event] of run.events.entries()) {
        if (run.burst !== true) await tick();
        if (index === run.events.length - 1) onBeforeTerminal();
        if (run.keepalive === true) controller.enqueue(encoder.encode(KEEPALIVE));
        controller.enqueue(encoder.encode(`event: ${event.method}\ndata: ${JSON.stringify(event)}\n\n`));
      }
      controller.close();
    },
  });
  return new HttpResponse(body, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache, no-transform' },
  });
}

export function threadFixture(overrides: Partial<AssistantThreadOut> = {}): AssistantThreadOut {
  return {
    id: 't-1',
    title: '',
    awaiting_approval: false,
    created_at: '2026-10-24T15:00:00Z',
    updated_at: '2026-10-24T15:00:00Z',
    ...overrides,
  };
}

/** A scripted run, or one built from the POSTed body (to echo the client's message id, as the server does). */
export type RunScript = ScriptedRun | ((body: unknown) => ScriptedRun);

export function assistantHandlers({
  runs,
  state = EMPTY_STATE,
  threads = [],
}: {
  runs: RunScript[];
  state?: unknown;
  threads?: AssistantThreadOut[];
}) {
  const queue = [...runs];
  const fake: FakeAssistant = { posted: [], state, threads };
  const startRun = async ({ request }: { request: Request }) => {
    const path = new URL(request.url).pathname;
    const body: unknown = await request.json();
    fake.posted.push({ path, body });
    const script = queue.shift();
    const run = typeof script === 'function' ? script(body) : script;
    if (run === undefined) {
      return HttpResponse.json({ code: 'conflict', message: 'No scripted run left.' }, { status: 409 });
    }
    return sseResponse(run, () => {
      fake.state = run.state;
    });
  };
  const handlers = [
    http.get('*/api/assistant/threads', () => HttpResponse.json(fake.threads)),
    http.post('*/api/assistant/threads', () => {
      const created = threadFixture({ id: `t-${String(fake.threads.length + 1)}` });
      fake.threads = [created, ...fake.threads];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get('*/api/assistant/threads/:threadId/state', () => HttpResponse.json(fake.state as object)),
    http.post('*/api/assistant/threads/:threadId/runs', startRun),
    http.post('*/api/assistant/threads/:threadId/interrupts/:interruptId', startRun),
    // The SDK's own history read (see AssistantTransport.apiUrl); the backend has no such route.
    http.post('*/api/assistant/threads/:threadId/history', () =>
      HttpResponse.json({ code: 'not_found', message: 'Not found.' }, { status: 404 }),
    ),
  ];
  return { fake, handlers };
}
