/*
 * The panel in the real app shell, over the real useStream + AssistantTransport, with the assistant API
 * faked by MSW (fixtures/handlers.ts). Approval cases hydrate the recorded interrupted state (STATE1).
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getItemsMock } from '../../api/generated/items/items.msw';
import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import { getPartnersMock } from '../../api/generated/partners/partners.msw';
import { getUsersMock } from '../../api/generated/users/users.msw';
import { reviewHandlers } from '../../test/fixtures/reviewHandlers';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import type { Role } from '../../ui/domain';
import { NAV_COLLAPSED_KEY } from '../../ui/layout/AppShell';
import { assistantHandlers, threadFixture } from './fixtures/handlers';
import type { RunScript, ScriptedRun } from './fixtures/handlers';
import { aiText, echoRun, EMPTY_STATE, lifecycle, values } from './fixtures/sse';
import { INTERRUPT_ID, RUN1, RUN2, STATE1, STATE2 } from './fixtures/wire';
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
  // The first wait covers the session gate and the whole route tree loading, which can pass 1 s under load.
  return screen.findByRole('complementary', { name: 'Assistant' }, { timeout: 5000 });
}

/** A run that reads CP-1042 (tool result links the item) and answers in Markdown. */
function itemRun(body: unknown): ScriptedRun {
  const { message } = body as { message: { id: string; content: string } };
  const human = { type: 'human', id: message.id, content: message.content };
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

  it('toggles with Ctrl+. even while typing, handing focus back to the toggle', async () => {
    const user = userEvent.setup();
    setup();
    const box = within(await panel()).getByRole('textbox', { name: 'Message the assistant' });
    await user.click(box);
    await user.keyboard('{Control>}.{/Control}');
    expect(screen.queryByRole('complementary', { name: 'Assistant' })).toBeNull();
    const toggle = screen.getByRole('button', { name: 'Assistant' });
    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAttribute('aria-keyshortcuts', 'Meta+. Control+.');
    await user.keyboard('{Control>}.{/Control}');
    expect(await panel()).toBeInTheDocument();
  });
});

describe('assistant toggle', () => {
  it('marks a draft waiting for approval even with the panel closed', async () => {
    setup({ open: false, threads: [threadFixture({ awaiting_approval: true })] });
    const toggle = await screen.findByRole('button', {
      name: 'Assistant, an email is waiting for your approval',
    });
    expect(toggle.querySelector('.app-assistant-toggle-dot')).not.toBeNull();
  });
});

describe('assistant panel beside narrow pages', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function narrowViewport() {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(width < 1600px)',
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
  }

  it('collapses the nav to the rail while open, without touching the saved choice, and restores it on close', async () => {
    const user = userEvent.setup();
    narrowViewport();
    setup();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    await panel();
    expect(nav).toHaveAttribute('data-collapsed', 'true');
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBeNull();

    await user.click(within(await panel()).getByRole('button', { name: 'Close assistant' }));
    expect(nav).not.toHaveAttribute('data-collapsed');
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBeNull();
  });

  it('still lets you expand the nav while the panel is open', async () => {
    const user = userEvent.setup();
    narrowViewport();
    setup();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    await panel();
    await user.click(screen.getByRole('button', { name: 'Expand navigation' }));
    expect(nav).not.toHaveAttribute('data-collapsed');
  });

  it('leaves the nav alone on wide screens', async () => {
    setup();
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    await panel();
    expect(nav).not.toHaveAttribute('data-collapsed');
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
      "Email compliance this week's re-reviews",
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
    setup({ runs: [itemRun], threads: [threadFixture()], activeThread: 't-1' });
    const region = await panel();
    await user.type(
      await within(region).findByRole('textbox', { name: 'Message the assistant' }),
      'What about CP-1042?{Enter}',
    );

    const strong = await within(region).findByText('two blocking findings');
    expect(within(region).getAllByText('What about CP-1042?')).toHaveLength(1); // echo reconciled by id
    expect(strong.tagName).toBe('STRONG');
    const tools = within(region).getByRole('list', { name: 'Tool calls' });
    const chip = within(tools).getByRole('listitem');
    expect(chip).toHaveTextContent('Read CP-1042');
    expect(chip).toHaveAttribute('data-status', 'finished');
    expect(within(chip).getByRole('link', { name: 'CP-1042' })).toHaveAttribute('href', '/items/1042');
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
    // Read-only, not disabled: focus stays in the box while the reply streams.
    expect(box).toHaveAttribute('readonly');
    expect(box).toHaveFocus();
    await user.click(stop);

    expect(await within(region).findByRole('button', { name: 'Send' })).toBeInTheDocument();
    expect(box).not.toHaveAttribute('readonly');
    // Whatever the server still sends after Stop is dropped (closing the stream cancels the run server-side).
    for (const event of aiText('a2', ['Too late.'])) server_?.enqueue(frame(event));
    server_?.enqueue(frame(lifecycle('completed')));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(within(region).queryByText('Too late.')).toBeNull();
  });

  it('on a 409, keeps your text, shows no unsent message, says what to do, and Retry sends it', async () => {
    const user = userEvent.setup();
    const { fake } = setup({ threads: [threadFixture()], activeThread: 't-1', runs: [echoRun('Done.')] });
    let refused = false;
    server.use(
      http.post('*/api/assistant/threads/:threadId/runs', () => {
        if (refused) return undefined; // the second try reaches the scripted run
        refused = true;
        return HttpResponse.json(
          { code: 'conflict', message: 'A reply is already running in this thread.' },
          { status: 409 },
        );
      }),
    );
    const region = await panel();
    const box = await within(region).findByRole('textbox', { name: 'Message the assistant' });
    await user.type(box, 'Which of those are re-reviews?{Enter}');

    const alert = await within(region).findByRole('alert');
    expect(alert).toHaveTextContent(
      'A reply is already running in this thread. Wait for it to finish, then send again.',
    );
    expect(box).toHaveValue('Which of those are re-reviews?');
    expect(within(region).queryByRole('log')).toBeNull(); // nothing was sent, so no conversation yet

    await user.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await within(region).findByText('Done.')).toBeInTheDocument();
    expect(within(region).getAllByText('Which of those are re-reviews?')).toHaveLength(1);
    expect(box).toHaveValue('');
    expect(fake.posted.at(-1)?.body).toMatchObject({
      message: { content: 'Which of those are re-reviews?' },
    });
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

    await user.click(within(draft).getByRole('button', { name: 'Send email' }));

    expect(await within(await panel()).findByText('Sent it.')).toBeInTheDocument();
    const sent = within(await panel())
      .getByText('Sent to a@clearpath.demo · approved by you')
      .closest('li');
    if (sent === null) throw new Error('expected the sent line');
    expect(within(sent).getByRole('link', { name: 'Open in Outbox' })).toHaveAttribute(
      'href',
      '/outbox?email=1',
    );
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

  it('says what the buttons do in email terms, not item-decision terms', async () => {
    pendingThread();
    const draft = await card();
    const buttons = within(draft)
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(buttons).toEqual(['Send email', 'Edit', "Don't send"]);
  });

  it('focuses To when editing, keeps the item in view, and Escape cancels', async () => {
    const user = userEvent.setup();
    const withItem = structuredClone(STATE1);
    const value = withItem.tasks[0]?.interrupts[0]?.value;
    if (value === undefined) throw new Error('fixture has no approval');
    value.args.item_key = 'CP-1042';
    const { fake } = setup({ state: withItem, threads: [threadFixture()], activeThread: 't-1' });
    const draft = await card();
    await user.click(within(draft).getByRole('button', { name: 'Edit' }));

    const form = within(draft).getByRole('form', { name: 'Edit email' });
    expect(within(form).getByRole('textbox', { name: 'To' })).toHaveFocus();
    expect(within(draft).getByRole('link', { name: 'CP-1042' })).toHaveAttribute('href', '/items/1042');

    await user.keyboard('{Escape}');
    expect(within(draft).queryByRole('form', { name: 'Edit email' })).toBeNull();
    expect(within(draft).getByRole('button', { name: 'Edit' })).toHaveFocus();
    expect(fake.posted).toEqual([]);
  });

  it('moves focus to the card when a draft arrives while you are in the panel', async () => {
    const user = userEvent.setup();
    setup({ runs: [{ events: RUN1, state: STATE1 }], threads: [threadFixture()], activeThread: 't-1' });
    const box = await within(await panel()).findByRole('textbox', { name: 'Message the assistant' });
    await user.type(box, 'hi{Enter}');
    const draft = await card();
    await waitFor(() => {
      expect(within(draft).getByRole('heading', { name: 'Email draft — needs your approval' })).toHaveFocus();
    });
    await user.tab();
    expect(within(draft).getByRole('button', { name: 'Send email' })).toHaveFocus();
  });

  it('rejects with an optional reason', async () => {
    const user = userEvent.setup();
    const { fake } = pendingThread();
    const draft = await card();
    await user.click(within(draft).getByRole('button', { name: "Don't send" }));
    const reason = within(draft).getByRole('textbox', { name: /Reason/ });
    expect(reason).toHaveFocus();
    await user.type(reason, 'Wrong team');
    await act(async () => {
      await user.click(within(draft).getByRole('button', { name: "Don't send" }));
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
