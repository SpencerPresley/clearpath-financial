/*
 * The assistant and Outbox API for e2e, layered over stubApi (register after it: Playwright tries the most
 * recently added route first). Runs are served as whole SSE bodies. Like the server, GET state reflects the
 * checkpoint after each run, and the run echoes the client's message id. Approving the draft writes the email
 * to the Outbox.
 */
import type { Page, Route } from '@playwright/test';

import type { AssistantThreadOut, OutboxEmailOut, ToolApprovalOut } from '../src/api/generated/model';
import { aiText, EMPTY_STATE, lifecycle, sseText, values } from '../src/features/assistant/fixtures/sse';
import type { WireEvent } from '../src/features/assistant/fixtures/wire';
import { NOW, REVIEWER } from '../src/test/fixtures/review';

export const INTERRUPT_ID = 'i-1';

export const APPROVAL: ToolApprovalOut = {
  type: 'tool_approval',
  tool_call_id: 'call-1',
  name: 'send_email',
  args: {
    to: ['compliance@clearpath.demo'],
    subject: 'CP-1 findings summary',
    body: 'CP-1 has two blocking findings: the APR range and the credit-score claim.',
    item_key: 'CP-1',
  },
  description: 'Tool execution requires approval',
};

export interface AssistantStub {
  posted: { path: string; body: unknown }[];
  outbox: OutboxEmailOut[];
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function sse(route: Route, events: WireEvent[]) {
  return route.fulfill({
    status: 200,
    contentType: 'text/event-stream',
    headers: { 'Cache-Control': 'no-cache, no-transform' },
    body: sseText(events, { keepalive: true }),
  });
}

export async function stubAssistant(page: Page): Promise<AssistantStub> {
  const stub: AssistantStub = { posted: [], outbox: [] };
  const threads: AssistantThreadOut[] = [];
  let state: unknown = EMPTY_STATE;
  let human: Record<string, unknown> = {};
  const draftTurn = {
    type: 'ai',
    id: 'a1',
    content: "I'll draft it for your approval.",
    tool_calls: [{ id: APPROVAL.tool_call_id, name: 'send_email', args: APPROVAL.args, type: 'tool_call' }],
  };

  await page.route('**/api/outbox', (route) => json(route, stub.outbox));

  await page.route('**/api/assistant/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\/assistant/, '');
    const method = request.method();
    const body: unknown = method === 'GET' ? undefined : request.postDataJSON();
    if (method !== 'GET') stub.posted.push({ path, body });

    if (path === '/threads' && method === 'GET') return json(route, threads);
    if (path === '/threads' && method === 'POST') {
      const thread: AssistantThreadOut = {
        id: '0b4c7a4e-0000-4000-8000-000000000001',
        title: '',
        awaiting_approval: false,
        created_at: NOW,
        updated_at: NOW,
      };
      threads.unshift(thread);
      return json(route, thread, 201);
    }
    if (/^\/threads\/[^/]+\/state$/.test(path)) return json(route, state);
    if (/^\/threads\/[^/]+\/history$/.test(path)) return json(route, []);
    if (/^\/threads\/[^/]+\/runs$/.test(path)) {
      const { message } = body as { message: { id: string; content: string } };
      human = { type: 'human', id: message.id, content: message.content };
      const thread = threads.at(0);
      if (thread !== undefined) Object.assign(thread, { title: message.content, awaiting_approval: true });
      state = {
        ...EMPTY_STATE,
        values: { messages: [human, draftTurn] },
        next: ['tools'],
        tasks: [{ id: 'task-1', name: 'tools', interrupts: [{ id: INTERRUPT_ID, value: APPROVAL }] }],
      };
      return sse(route, [
        lifecycle('running'),
        values([human]),
        ...aiText('a1', ["I'll draft it ", 'for your approval.']),
        values([human, draftTurn]),
        {
          type: 'event',
          method: 'input.requested',
          params: { namespace: [], data: { interrupt_id: INTERRUPT_ID, payload: APPROVAL } },
        },
        lifecycle('interrupted'),
      ]);
    }
    if (path === `/threads/${threads.at(0)?.id ?? ''}/interrupts/${INTERRUPT_ID}`) {
      const toolMessage = {
        type: 'tool',
        id: 't1',
        name: 'send_email',
        tool_call_id: APPROVAL.tool_call_id,
        content: 'Sent to compliance@clearpath.demo.',
        status: 'success',
        artifact: { outcome: 'sent', outbox_id: 1, to: APPROVAL.args.to, item_keys: ['CP-1'] },
      };
      const done = { type: 'ai', id: 'a2', content: 'Sent. It is in the Outbox.', tool_calls: [] };
      const messages = [human, draftTurn, toolMessage, done];
      stub.outbox.push({
        id: 1,
        to: APPROVAL.args.to,
        subject: APPROVAL.args.subject,
        body: APPROVAL.args.body,
        html_body: `<p>${APPROVAL.args.body}</p>`,
        item_id: 1,
        thread_id: threads.at(0)?.id ?? '',
        sent_at: NOW,
        requested_by: REVIEWER,
        approved_by: REVIEWER,
      });
      const thread = threads.at(0);
      if (thread !== undefined) thread.awaiting_approval = false;
      state = { ...EMPTY_STATE, values: { messages } };
      return sse(route, [
        lifecycle('running'),
        values([human, draftTurn, toolMessage]),
        ...aiText('a2', ['Sent. ', 'It is in the Outbox.']),
        values(messages),
        lifecycle('completed'),
      ]);
    }
    return json(route, { code: 'not_found', message: `No stub for ${method} ${path}` }, 404);
  });
  return stub;
}
