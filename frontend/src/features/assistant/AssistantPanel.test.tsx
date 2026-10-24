/*
 * The panel in the real app shell, over the real useStream + AssistantTransport, with the assistant API
 * faked by MSW (fixtures/handlers.ts). Approval cases hydrate the recorded interrupted state (STATE1).
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';

import { getItemsMock } from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getPartnersMock } from '../../api/generated/partners/partners.msw';
import { getUsersMock } from '../../api/generated/users/users.msw';
import { reviewHandlers } from '../../test/fixtures/reviewHandlers';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import type { Role } from '../../ui/domain';
import { assistantHandlers, threadFixture } from './fixtures/handlers';
import type { RunScript, ScriptedRun } from './fixtures/handlers';
import { aiText, echoRun, EMPTY_STATE, lifecycle, values } from './fixtures/sse';
import { INTERRUPT_ID, RUN2, STATE1, STATE2 } from './fixtures/wire';
import { ASSISTANT_OPEN_KEY, threadKey } from './storage';

const VIEWER_ID = 5;

function setup({
  runs = [],
  state = EMPTY_STATE,
  threads = [],
  roles = ['reviewer'],
  open = true,
  activeThread,
  path = '/',
}: {
  runs?: RunScript[];
  state?: unknown;
  threads?: ReturnType<typeof threadFixture>[];
  roles?: Role[];
  open?: boolean;
  activeThread?: string;
  path?: string;
} = {}) {
  if (open) window.localStorage.setItem(ASSISTANT_OPEN_KEY, 'true');
  if (activeThread !== undefined) window.localStorage.setItem(threadKey(VIEWER_ID), activeThread);
  const assistant = assistantHandlers({ runs, state, threads });
  server.use(
    ...getItemsMock(),
    ...getUsersMock(),
    ...getPartnersMock(),
    ...reviewHandlers(),
    getGetMeMockHandler({
      id: VIEWER_ID,
      display_name: 'Dana Reyes',
      email: 'dana@clearpath.demo',
      roles,
      effective_roles: roles,
      is_available: true,
    }),
    ...assistant.handlers,
  );
  const app = renderApp(path);
  return { ...app, fake: assistant.fake };
}

async function panel() {
  return screen.findByRole('complementary', { name: 'Assistant' });
}

/** A run that reads CP-1042 (tool result links the item) and answers in Markdown. */
function itemRun(): ScriptedRun {
  const human = { type: 'human', id: 'u1', content: 'What about CP-1042?' };
  const call = { id: 'c1', name: 'get_item', args: { item_key: 'CP-1042' }, type: 'tool_call' };
  const ai1 = { type: 'ai', id: 'a1', content: '', tool_calls: [call] };
  const tool = {
    type: 'tool',
    id: 't1',
    name: 'get_item',
    tool_call_id: 'c1',
    content: '{"key":"CP-1042"}',
    status: 'success',
    artifact: { item_keys: ['CP-1042'] },
  };
  const text = 'It has **two blocking findings**; see CP-1042.';
  const ai2 = { type: 'ai', id: 'a2', content: text, tool_calls: [] };
  const messages = [human, ai1, tool, ai2];
  return {
    events: [
      lifecycle('running'),
      values([human]),
      values([human, ai1]),
      values([human, ai1, tool]),
      ...aiText('a2', [text]),
      values(messages),
      lifecycle('completed'),
    ],
    state: { ...EMPTY_STATE, values: { messages } },
  };
}

afterEach(() => {
  window.localStorage.clear();
});

describe('assistant panel toggle', () => {
  it('opens from the topbar, persists, and closes back to the toggle', async () => {
    const user = userEvent.setup();
    const first = setup({ open: false });
    const toggle = await screen.findByRole('button', { name: 'Assistant' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('complementary', { name: 'Assistant' })).toBeNull();

    await user.click(toggle);
    expect(await panel()).toHaveAttribute('id', 'assistant-panel');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAttribute('aria-controls', 'assistant-panel');
    expect(window.localStorage.getItem(ASSISTANT_OPEN_KEY)).toBe('true');
    // The page stays usable: the panel is a region beside main, not a modal.
    expect(screen.getByRole('main')).toBeInTheDocument();

    first.unmount();
    setup();
    expect(await panel()).toBeInTheDocument();

    await user.click(within(await panel()).getByRole('button', { name: 'Close assistant' }));
    expect(screen.queryByRole('complementary', { name: 'Assistant' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Assistant' })).toHaveFocus();
    expect(window.localStorage.getItem(ASSISTANT_OPEN_KEY)).toBe('false');
  });

  it('toggles with Ctrl+. even while typing', async () => {
    const user = userEvent.setup();
    setup();
    const box = within(await panel()).getByRole('textbox', { name: 'Message the assistant' });
    await user.click(box);
    await user.keyboard('{Control>}.{/Control}');
    expect(screen.queryByRole('complementary', { name: 'Assistant' })).toBeNull();
    await user.keyboard('{Control>}.{/Control}');
    expect(await panel()).toBeInTheDocument();
  });
});

describe('assistant conversation', () => {
  it('offers three asks for the role and fills the box with one', async () => {
    const user = userEvent.setup();
    setup();
    const asks = within(await panel()).getByRole('list', { name: 'Example questions' });
    expect(
      within(asks)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([
      "What's waiting on me?",
      'Find precedent for “no impact to your credit score”',
      'Email compliance a summary of CP-',
    ]);
    await user.click(within(asks).getByRole('button', { name: "What's waiting on me?" }));
    expect(screen.getByRole('textbox', { name: 'Message the assistant' })).toHaveValue(
      "What's waiting on me?",
    );
  });

  it('creates the thread on the first send, streams the reply, and remembers the thread', async () => {
    const user = userEvent.setup();
    const { fake } = setup({ runs: [echoRun('Nothing is waiting on you.')] });
    const region = await panel();
    expect(within(region).getByRole('heading', { name: 'New thread' })).toBeInTheDocument();

    await user.type(within(region).getByRole('textbox', { name: 'Message the assistant' }), 'hi{Enter}');

    expect(await within(region).findByText('Nothing is waiting on you.')).toBeInTheDocument();
    expect(fake.threads.map((t) => t.id)).toEqual(['t-1']);
    expect(fake.posted).toHaveLength(1);
    expect(fake.posted[0]?.path).toBe('/api/assistant/threads/t-1/runs');
    expect(fake.posted[0]?.body).toMatchObject({ message: { content: 'hi' } });
    expect(window.localStorage.getItem(threadKey(VIEWER_ID))).toBe('t-1');
    expect(within(region).getByText('hi')).toBeInTheDocument();
  });

  it('renders Markdown, links item keys, and lists tool calls under the turn that made them', async () => {
    const user = userEvent.setup();
    setup({ runs: [itemRun()], threads: [threadFixture()], activeThread: 't-1' });
    const region = await panel();
    await user.type(
      await within(region).findByRole('textbox', { name: 'Message the assistant' }),
      'What about CP-1042?{Enter}',
    );

    const strong = await within(region).findByText('two blocking findings');
    expect(strong.tagName).toBe('STRONG');
    const tools = within(region).getByRole('list', { name: 'Tool calls' });
    const chip = within(tools).getByRole('listitem');
    expect(chip).toHaveTextContent('Read CP-1042');
    expect(chip).toHaveAttribute('data-status', 'finished');
    const links = within(region).getAllByRole('link', { name: 'CP-1042' });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toHaveAttribute('href', '/items/1042');
  });

  it('sends the open item as context and says so in the composer', async () => {
    const user = userEvent.setup();
    const { fake } = setup({
      path: '/items/1042',
      runs: [echoRun('Done.')],
      threads: [threadFixture()],
      activeThread: 't-1',
    });
    const region = await panel();
    expect(await within(region).findByText('Context: CP-1042')).toBeInTheDocument();
    await user.type(
      within(region).getByRole('textbox', { name: 'Message the assistant' }),
      'Summarize{Enter}',
    );
    await within(region).findByText('Done.');
    expect(fake.posted[0]?.body).toMatchObject({ message: { content: 'Summarize' }, item_id: 1042 });
  });

  it('locks the composer while a reply runs, and Stop stops reading the stream', async () => {
    const user = userEvent.setup();
    setup({ threads: [threadFixture()], activeThread: 't-1' });
    const encoder = new TextEncoder();
    const frame = (event: unknown) => encoder.encode(`data: ${JSON.stringify(event)}\n\n`);
    let server_: ReadableStreamDefaultController<Uint8Array> | undefined;
    server.use(
      http.post('*/api/assistant/threads/:threadId/runs', () => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            server_ = controller;
            controller.enqueue(frame(lifecycle('running')));
            for (const event of aiText('a1', ['Looking '])) controller.enqueue(frame(event));
          },
        });
        return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } });
      }),
    );
    const region = await panel();
    const box = await within(region).findByRole('textbox', { name: 'Message the assistant' });
    await user.type(box, 'hi{Enter}');

    const stop = await within(region).findByRole('button', { name: 'Stop' });
    expect(box).toBeDisabled();
    await user.click(stop);

    expect(await within(region).findByRole('button', { name: 'Send' })).toBeInTheDocument();
    expect(box).toBeEnabled();
    // Whatever the server still sends after Stop is dropped (closing the stream cancels the run server-side).
    for (const event of aiText('a2', ['Too late.'])) server_?.enqueue(frame(event));
    server_?.enqueue(frame(lifecycle('completed')));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(region).queryByText('Too late.')).toBeNull();
  });

  it('shows the API line when a reply is already running (409)', async () => {
    const user = userEvent.setup();
    setup({ threads: [threadFixture()], activeThread: 't-1' });
    server.use(
      http.post('*/api/assistant/threads/:threadId/runs', () =>
        HttpResponse.json({ code: 'conflict', message: 'A reply is already running.' }, { status: 409 }),
      ),
    );
    const region = await panel();
    await user.type(
      await within(region).findByRole('textbox', { name: 'Message the assistant' }),
      'hi{Enter}',
    );
    expect(await within(region).findByRole('alert')).toHaveTextContent('A reply is already running.');
  });
});

describe('email approval', () => {
  const pendingThread = () =>
    setup({
      state: STATE1,
      runs: [{ events: RUN2, state: STATE2 }],
      threads: [threadFixture({ title: 'hi', awaiting_approval: true })],
      activeThread: 't-1',
    });

  async function card() {
    return within(await panel()).findByRole('region', { name: 'Email draft — needs your approval' });
  }

  it('reappears from state after a reload, locks the composer, and Approve resumes the run', async () => {
    const user = userEvent.setup();
    const { fake } = pendingThread();
    const draft = await card();
    expect(within(draft).getByRole('list', { name: 'Recipients' })).toHaveTextContent('a@clearpath.demo');
    expect(within(draft).getByText('S')).toBeInTheDocument();
    expect(within(draft).getByText('Nothing is sent until you approve.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Message the assistant' })).toBeDisabled();
    expect(within(await panel()).getByText('Email waiting for your approval')).toBeInTheDocument();

    await user.click(within(draft).getByRole('button', { name: 'Approve' }));

    expect(await within(await panel()).findByText('Sent it.')).toBeInTheDocument();
    expect(fake.posted).toEqual([
      { path: `/api/assistant/threads/t-1/interrupts/${INTERRUPT_ID}`, body: { type: 'approve' } },
    ]);
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'Email draft — needs your approval' })).toBeNull();
    });
  });

  it('maps a 422 on an edited recipient onto the To field, then sends the fixed edit', async () => {
    const user = userEvent.setup();
    const { fake } = pendingThread();
    let attempts = 0;
    server.use(
      http.post('*/api/assistant/threads/:threadId/interrupts/:interruptId', async ({ request }) => {
        attempts += 1;
        if (attempts > 1) return undefined; // fall through to the scripted resume
        fake.posted.push({ path: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json(
          {
            code: 'invalid_input',
            message: 'Check the highlighted fields.',
            fields: [
              {
                loc: ['body', 'edited_action', 'args', 'to'],
                message: 'Not an internal address: x@evil.example',
                type: 'value_error',
              },
            ],
          },
          { status: 422 },
        );
      }),
    );
    const draft = await card();
    await user.click(within(draft).getByRole('button', { name: 'Edit' }));
    const form = within(draft).getByRole('form', { name: 'Edit email' });
    const to = within(form).getByRole('textbox', { name: 'To' });
    await user.clear(to);
    await user.type(to, 'a@clearpath.demo, x@evil.example');
    await user.clear(within(form).getByRole('textbox', { name: 'Subject' }));
    await user.type(within(form).getByRole('textbox', { name: 'Subject' }), 'Findings');
    await user.click(within(form).getByRole('button', { name: 'Send edited' }));

    expect(await within(form).findByText('Not an internal address: x@evil.example')).toBeInTheDocument();
    expect(fake.posted[0]?.body).toEqual({
      type: 'edit',
      edited_action: {
        name: 'send_email',
        args: { to: ['a@clearpath.demo', 'x@evil.example'], subject: 'Findings', body: 'B', item_key: null },
      },
    });
    // The 422 belongs to the form, not the panel's error line.
    expect(within(await panel()).queryByText('Check the highlighted fields.')).toBeNull();

    await user.clear(to);
    await user.type(to, 'a@clearpath.demo');
    await user.click(within(form).getByRole('button', { name: 'Send edited' }));
    expect(await within(await panel()).findByText('Sent it.')).toBeInTheDocument();
    expect(fake.posted[1]?.body).toMatchObject({
      type: 'edit',
      edited_action: { args: { to: ['a@clearpath.demo'], subject: 'Findings' } },
    });
  });

  it('rejects with an optional reason', async () => {
    const user = userEvent.setup();
    const { fake } = pendingThread();
    const draft = await card();
    await user.click(within(draft).getByRole('button', { name: 'Reject' }));
    await user.type(within(draft).getByRole('textbox', { name: /Reason/ }), 'Wrong team');
    await act(async () => {
      await user.click(within(draft).getByRole('button', { name: 'Reject' }));
    });
    await waitFor(() => {
      expect(fake.posted).toHaveLength(1);
    });
    expect(fake.posted[0]?.body).toEqual({ type: 'reject', message: 'Wrong team' });
  });

  it('marks threads waiting on approval in the switcher', async () => {
    const user = userEvent.setup();
    setup({
      threads: [
        threadFixture({ id: 't-1', title: 'Queue this week' }),
        threadFixture({ id: 't-2', title: 'Email CP-1042 findings', awaiting_approval: true }),
      ],
      activeThread: 't-1',
    });
    const region = await panel();
    expect(await within(region).findByRole('heading', { name: 'Queue this week' })).toBeInTheDocument();
    await user.click(within(region).getByRole('button', { name: /Threads/ }));
    const menu = await screen.findByRole('menu', { name: 'Threads' });
    const pending = within(menu).getByRole('menuitemradio', { name: /Email CP-1042 findings/ });
    expect(pending).toHaveTextContent('Pending approval');
    await user.click(pending);
    expect(
      await within(region).findByRole('heading', { name: 'Email CP-1042 findings' }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(threadKey(VIEWER_ID))).toBe('t-2');
  });
});
