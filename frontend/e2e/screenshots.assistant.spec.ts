/*
 * UI-review screenshots of the assistant panel and the Outbox (spec §8.4). Skipped unless SCREENSHOTS=1:
 *   SCREENSHOTS=1 npx playwright test e2e/screenshots.assistant.spec.ts
 * Output: docs/plan/reviews/ui/assistant/<state>-<width>.png, plus keyboard/ARIA notes in keyboard-<width>.json.
 *
 * Layers a per-shot scene over stubAssistant (registered after it, so it's tried first; anything it doesn't
 * serve falls back): seeded threads are hydrated from GET state, so most states don't replay a run. The
 * approval states drive stubAssistant's real draft -> approve flow. Streaming needs a body that stays open,
 * which route.fulfill can't do, so that shot answers /runs from a fetch override in the page.
 */
import { writeFileSync } from 'node:fs';

import { expect, test } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

import type { AssistantThreadOut, OutboxEmailOut } from '../src/api/generated/model';
import { aiText, EMPTY_STATE, lifecycle, sseText, values } from '../src/features/assistant/fixtures/sse';
import type { WireEvent } from '../src/features/assistant/fixtures/wire';
import { NOW, REVIEWER } from '../src/test/fixtures/review';
import { stubApi as stubQueueApi } from './api.ts';
import { APPROVAL, stubAssistant } from './stubAssistant';
import { stubApi as stubReviewApi } from './stubApi';

const OUT = '../docs/plan/reviews/ui/assistant';
const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
] as const;

test.skip(process.env.SCREENSHOTS !== '1', 'set SCREENSHOTS=1 to capture UI-review screenshots');

// ---- Fixtures ---------------------------------------------------------------------------------------

const minutesAgo = (m: number) => new Date(Date.parse(NOW) - m * 60_000).toISOString();

const T_ANSWER = '0b4c7a4e-0000-4000-8000-0000000000a1';
const T_PENDING = '0b4c7a4e-0000-4000-8000-0000000000a2';
const T_REJECTED = '0b4c7a4e-0000-4000-8000-0000000000a3';
const T_REFUSED = '0b4c7a4e-0000-4000-8000-0000000000a4';
const T_SENT = '0b4c7a4e-0000-4000-8000-0000000000a5';

function thread(id: string, title: string, ageMin: number, awaiting = false): AssistantThreadOut {
  return {
    id,
    title,
    awaiting_approval: awaiting,
    created_at: minutesAgo(ageMin + 5),
    updated_at: minutesAgo(ageMin),
  };
}

const THREADS: AssistantThreadOut[] = [
  thread(T_ANSWER, "What's waiting on me?", 2),
  thread(T_PENDING, 'Email compliance a summary of CP-1047', 40, true),
  thread(T_REJECTED, 'Draft a note to Sam about CP-1031', 180),
  thread(T_SENT, 'Send the weekly re-review digest to the leads', 60 * 26),
  thread(T_REFUSED, 'Forward the CP-1044 findings to the partner', 60 * 24 * 3),
];

const HUMAN_ASK = { type: 'human', id: 'u1', content: "What's waiting on me? Anything blocking?" };
const AI_TOOLS = {
  type: 'ai',
  id: 'a1',
  content: '',
  tool_calls: [
    {
      id: 'c1',
      name: 'search_items',
      args: { assignee: 'me', status: ['submitted', 'in_review'] },
      type: 'tool_call',
    },
    { id: 'c2', name: 'get_item', args: { item_key: 'CP-1047' }, type: 'tool_call' },
    { id: 'c3', name: 'get_offer_terms', args: { product: 'personal_loan' }, type: 'tool_call' },
  ],
};
const TOOL_RESULTS = [
  {
    type: 'tool',
    id: 't1',
    name: 'search_items',
    tool_call_id: 'c1',
    content: '4 items',
    status: 'success',
    artifact: { item_keys: ['CP-1047', 'CP-1044', 'CP-1031', 'CP-1050'] },
  },
  {
    type: 'tool',
    id: 't2',
    name: 'get_item',
    tool_call_id: 'c2',
    content: 'CP-1047',
    status: 'success',
    artifact: { item_keys: ['CP-1047'] },
  },
  {
    type: 'tool',
    id: 't3',
    name: 'get_offer_terms',
    tool_call_id: 'c3',
    content: '…',
    status: 'success',
    artifact: null,
  },
];
const ANSWER_MD = [
  'Four items are assigned to you. Two have blocking findings:',
  '',
  '| Item | Status | Blocking | Age |',
  '|---|---|---|---|',
  '| CP-1047 | In review | 2 | 3d |',
  '| CP-1031 | Submitted | 1 | 5d |',
  '',
  'On CP-1047 the AI suggestions are:',
  '',
  '- **Rate claim may need the full APR range** · Reg Z 1026.24(a). The ad says “as low as 5.99% APR”; current terms run 5.99–35.99%.',
  '- “No impact to your credit score” may need a qualifier · the prequal uses a soft pull only.',
  '',
  'CP-1044 and CP-1050 have warnings only.',
].join('\n');
const AI_ANSWER = { type: 'ai', id: 'a2', content: ANSWER_MD, tool_calls: [] };
const ANSWER_MESSAGES = [HUMAN_ASK, AI_TOOLS, ...TOOL_RESULTS, AI_ANSWER];

function stateOf(messages: readonly Record<string, unknown>[]) {
  return { ...EMPTY_STATE, values: { messages } };
}

const PENDING_APPROVAL = {
  ...APPROVAL,
  tool_call_id: 'p-call',
  args: {
    to: ['compliance@clearpath.demo', 'priya.raman@clearpath.demo'],
    subject: 'CP-1047 findings summary',
    body: [
      'Hi team,',
      '',
      'CP-1047 (Personal loan landing page, LendFast) has two open blocking findings:',
      '',
      '1. Rate claim may need the full APR range (Reg Z 1026.24(a)).',
      '2. “No impact to your credit score” may need a soft-pull qualifier.',
      '',
      'I have requested changes from the partner. No decision yet.',
      '',
      'Dana',
    ].join('\n'),
    item_key: 'CP-1047',
  },
};
const PENDING_STATE = {
  ...EMPTY_STATE,
  values: {
    messages: [
      { type: 'human', id: 'pu1', content: 'Email compliance a summary of CP-1047' },
      {
        type: 'ai',
        id: 'pa1',
        content: "Here's a draft. Nothing is sent until you approve it.",
        tool_calls: [{ id: 'p-call', name: 'send_email', args: PENDING_APPROVAL.args, type: 'tool_call' }],
      },
    ],
  },
  next: ['tools'],
  tasks: [{ id: 'task-p', name: 'tools', interrupts: [{ id: 'i-p', value: PENDING_APPROVAL }] }],
};

const sendCall = (id: string, to: string[], subject: string) => ({
  type: 'ai',
  id: `${id}-ai`,
  content: '',
  tool_calls: [
    { id, name: 'send_email', args: { to, subject, body: '…', item_key: null }, type: 'tool_call' },
  ],
});
const REJECTED_MESSAGES = [
  { type: 'human', id: 'ru1', content: 'Draft a note to Sam about CP-1031' },
  sendCall('r-call', ['sam.okafor@clearpath.demo'], 'CP-1031 needs the full APR range'),
  {
    type: 'tool',
    id: 'rt1',
    name: 'send_email',
    tool_call_id: 'r-call',
    content: "The user declined to send this email. Don't send it again unless they ask.",
    status: 'error',
    artifact: { outcome: 'declined', to: ['sam.okafor@clearpath.demo'], item_keys: ['CP-1031'] },
  },
  {
    type: 'ai',
    id: 'ra2',
    content: "Understood, I won't send it. Want me to change the draft?",
    tool_calls: [],
  },
];
const REFUSED_MESSAGES = [
  { type: 'human', id: 'fu1', content: 'Forward the CP-1044 findings to the partner' },
  sendCall('f-call', ['marketing@lendfast.example'], 'CP-1044 findings'),
  {
    type: 'tool',
    id: 'ft1',
    name: 'send_email',
    tool_call_id: 'f-call',
    content:
      'Not sent and not shown to the user. Not an internal address: marketing@lendfast.example. Only staff directory addresses receive email.',
    status: 'error',
    artifact: {
      outcome: 'blocked',
      refused: ['marketing@lendfast.example'],
      reason: 'Not an internal address: marketing@lendfast.example',
      to: ['marketing@lendfast.example'],
      item_keys: ['CP-1044'],
    },
  },
  {
    type: 'ai',
    id: 'fa2',
    content:
      "I can't email marketing@lendfast.example: only ClearPath staff addresses can receive email from here. I can draft the summary for you to send to the partner yourself.",
    tool_calls: [],
  },
];

const html = (
  paragraphs: string[],
  itemKey: string | null,
  requester: string,
  approver: string,
) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${itemKey ?? 'ClearPath'}</title></head>
<body style="font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.5; color: #1f2328;">
${paragraphs.map((p) => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('\n')}
${itemKey === null ? '' : `<p><a href="https://review.clearpath.demo/items/${itemKey.slice(3)}">${itemKey}</a>: Personal loan landing page</p>`}
<hr style="border: 0; border-top: 1px solid #d0d7de;">
<p style="color: #59636e; font-size: 12px;">Drafted by the ClearPath assistant for ${requester}. Approved by ${approver}.</p>
</body></html>`;

const DANA = REVIEWER;
const PRIYA = { id: 4, name: 'Priya Raman' };
const SAM = { id: 3, name: 'Sam Okafor' };

const OUTBOX: OutboxEmailOut[] = [
  {
    id: 4,
    to: ['compliance@clearpath.demo', 'priya.raman@clearpath.demo'],
    subject: 'CP-1047 findings summary',
    body: PENDING_APPROVAL.args.body,
    html_body: html(PENDING_APPROVAL.args.body.split('\n\n'), 'CP-1047', DANA.name, DANA.name),
    item_id: 1047,
    thread_id: T_PENDING,
    sent_at: minutesAgo(12),
    requested_by: DANA,
    approved_by: DANA,
  },
  {
    id: 3,
    to: ['priya.raman@clearpath.demo', 'sam.okafor@clearpath.demo', 'compliance-leads@clearpath.demo'],
    subject: 'Weekly re-review digest: 6 waiting on review, 2 re-reviews after the October rate change',
    body: 'Six items are waiting on review…',
    html_body: html(
      [
        'Six items are waiting on review and two approved items need re-review after the October 20 rate change.',
      ],
      null,
      SAM.name,
      PRIYA.name,
    ),
    item_id: null,
    thread_id: T_SENT,
    sent_at: minutesAgo(60 * 26),
    requested_by: SAM,
    approved_by: PRIYA,
  },
  {
    id: 2,
    to: ['sam.okafor@clearpath.demo'],
    subject: 'CP-1031 needs the full APR range before re-approval',
    body: 'Sam, CP-1031 still shows only the lowest APR…',
    html_body: html(
      ['Sam, CP-1031 still shows only the lowest APR. Can you ask LendFast for the range?'],
      'CP-1031',
      DANA.name,
      DANA.name,
    ),
    item_id: 1031,
    thread_id: T_REJECTED,
    sent_at: minutesAgo(60 * 24 * 2),
    requested_by: DANA,
    approved_by: DANA,
  },
  {
    id: 1,
    to: ['compliance@clearpath.demo'],
    subject: 'Plain-text note: offer terms updated',
    body: 'Offer terms for personal loans changed on October 20.\n\nTwo approved items reference the old APR range.',
    html_body: '',
    item_id: null,
    thread_id: T_SENT,
    sent_at: minutesAgo(60 * 24 * 4),
    requested_by: PRIYA,
    approved_by: PRIYA,
  },
];

// ---- Scene: a per-shot override over stubAssistant ----------------------------------------------------

type Handler = (route: Route, body: unknown) => Promise<void>;

interface Scene {
  /** Which base API stub: the queue fixtures (`/`), or the review fixtures (`/items/1`, default). */
  base?: 'queue' | 'review';
  /** Panel open on load, on this thread (null: open on a new thread). Undefined: closed. */
  open?: string | null;
  threads?: AssistantThreadOut[];
  states?: Record<string, unknown>;
  runs?: Handler;
  interrupts?: Handler;
  outbox?: OutboxEmailOut[] | 'hang' | number;
  /** SSE text for /runs served by a fetch override that never closes the body. */
  hangRun?: string;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function setup(page: Page, scene: Scene) {
  if (scene.base === 'queue') await stubQueueApi(page);
  else await stubReviewApi(page);
  const stub = await stubAssistant(page);

  await page.addInitScript(
    ({ open, hangRun }) => {
      if (open !== undefined) {
        window.localStorage.setItem('clearpath.assistant.open', 'true');
        for (const id of [21, 2]) {
          if (open === null) window.localStorage.removeItem(`clearpath.assistant.thread.${String(id)}`);
          else window.localStorage.setItem(`clearpath.assistant.thread.${String(id)}`, open);
        }
      }
      if (hangRun !== undefined) {
        const original = window.fetch.bind(window);
        window.fetch = (input, init) => {
          const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
          if (/\/api\/assistant\/threads\/[^/]+\/runs$/.test(url)) {
            // Echo the client's message id, as the server does, so the optimistic message is replaced.
            const sent = JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as {
              message: { id: string };
            };
            const bytes = new TextEncoder().encode(hangRun.replaceAll('__HUMAN_ID__', sent.message.id));
            const body = new ReadableStream<Uint8Array>({
              start(controller) {
                controller.enqueue(bytes); // and never close: the run is still going
              },
            });
            return Promise.resolve(
              new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
            );
          }
          return original(input, init);
        };
      }
    },
    { open: scene.open, hangRun: scene.hangRun },
  );

  await page.route('**/api/assistant/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\/assistant/, '');
    const method = request.method();
    const body: unknown = method === 'GET' ? undefined : request.postDataJSON();
    if (path === '/threads' && method === 'GET' && scene.threads !== undefined) {
      return json(route, scene.threads);
    }
    const state = /^\/threads\/([^/]+)\/state$/.exec(path);
    const seeded = state === null ? undefined : scene.states?.[state[1]];
    if (seeded !== undefined) return json(route, seeded);
    if (/^\/threads\/[^/]+\/runs$/.test(path) && scene.runs !== undefined) return scene.runs(route, body);
    if (path.includes('/interrupts/') && scene.interrupts !== undefined) return scene.interrupts(route, body);
    return route.fallback();
  });

  if (scene.outbox !== undefined) {
    const outbox = scene.outbox;
    await page.route('**/api/outbox', async (route) => {
      if (outbox === 'hang') return; // never answers
      if (typeof outbox === 'number') {
        return json(
          route,
          { code: 'server_error', message: 'The outbox is temporarily unavailable.' },
          outbox,
        );
      }
      return json(route, outbox);
    });
  }
  return stub;
}

const panelOf = (page: Page) => page.getByRole('complementary', { name: 'Assistant' });
const boxOf = (page: Page) => panelOf(page).getByRole('textbox', { name: 'Message the assistant' });
const cardOf = (page: Page) =>
  panelOf(page).getByRole('region', { name: 'Email draft — needs your approval' });

async function ask(page: Page, text: string) {
  await boxOf(page).fill(text);
  await boxOf(page).press('Enter');
}

/** Open a new thread via the toggle and get stubAssistant's draft up for approval. */
async function draftForApproval(page: Page) {
  await page.getByRole('button', { name: 'Assistant' }).click();
  await ask(page, 'Email compliance a summary of CP-1');
  await expect(cardOf(page)).toBeVisible();
}

const ALL_THREADS = {
  threads: THREADS,
  states: {
    [T_ANSWER]: stateOf(ANSWER_MESSAGES),
    [T_PENDING]: PENDING_STATE,
    [T_REJECTED]: stateOf(REJECTED_MESSAGES),
    [T_REFUSED]: stateOf(REFUSED_MESSAGES),
  },
} satisfies Partial<Scene>;

const STREAM_HUMAN = { ...HUMAN_ASK, id: '__HUMAN_ID__' };

const STREAM_PARTIAL = sseText(
  [
    lifecycle('running'),
    values([STREAM_HUMAN]),
    values([STREAM_HUMAN, AI_TOOLS]),
    ...(['c1', 'c2'] as const).map((id, i): WireEvent => ({
      type: 'event',
      method: 'tools',
      params: {
        namespace: [],
        data: {
          event: 'tool-finished',
          tool_call_id: id,
          output: TOOL_RESULTS[i],
        },
      },
    })),
    {
      type: 'event',
      method: 'tools',
      params: {
        namespace: [],
        data: {
          event: 'tool-started',
          tool_call_id: 'c3',
          tool_name: 'get_offer_terms',
          input: { product: 'personal_loan' },
        },
      },
    },
    values([STREAM_HUMAN, AI_TOOLS, TOOL_RESULTS[0] ?? {}, TOOL_RESULTS[1] ?? {}]),
  ],
  { keepalive: true },
);

const STREAM_TEXT = sseText(
  [
    lifecycle('running'),
    values([STREAM_HUMAN]),
    values([STREAM_HUMAN, AI_TOOLS]),
    values([STREAM_HUMAN, AI_TOOLS, ...TOOL_RESULTS]),
    // Deltas without content-block-finish / message-finish: mid-sentence.
    ...aiText('a2', [
      'Four items are assigned to you. ',
      'Two have blocking ',
      'findings:\n\n| Item | Status |',
    ]).slice(0, -2),
  ],
  { keepalive: true },
);

// ---- Shots --------------------------------------------------------------------------------------------

interface Shot {
  name: string;
  path?: string;
  scene: Scene;
  ready?: (page: Page) => Promise<void>;
}

const shots: Shot[] = [
  {
    name: 'closed',
    scene: { base: 'queue' },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      // Keyboard focus shows the tooltip at once (and the focus ring on the navy topbar).
      await page.keyboard.press('Shift');
      await page.getByRole('button', { name: 'Assistant' }).focus();
      await expect(page.getByRole('tooltip')).toBeVisible();
    },
  },
  {
    name: 'empty-thread',
    scene: { base: 'queue', threads: THREADS },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await page.getByRole('button', { name: 'Assistant' }).click();
      await expect(boxOf(page)).toBeFocused();
    },
  },
  {
    name: 'thread-list',
    scene: { base: 'queue', open: T_ANSWER, ...ALL_THREADS },
    ready: async (page) => {
      await expect(panelOf(page).getByText('Four items are assigned to you.')).toBeVisible();
      await panelOf(page).getByRole('button', { name: 'Threads' }).click();
      await expect(page.getByRole('menu')).toBeVisible();
    },
  },
  {
    name: 'streaming-tools',
    scene: { base: 'queue', threads: [], hangRun: STREAM_PARTIAL },
    ready: async (page) => {
      await page.getByRole('button', { name: 'Assistant' }).click();
      await ask(page, HUMAN_ASK.content);
      await expect(panelOf(page).getByRole('button', { name: 'Stop' })).toBeVisible();
      await expect(panelOf(page).getByText('Checking offer terms')).toBeVisible();
    },
  },
  {
    name: 'streaming-text',
    scene: { base: 'queue', threads: [], hangRun: STREAM_TEXT },
    ready: async (page) => {
      await page.getByRole('button', { name: 'Assistant' }).click();
      await ask(page, HUMAN_ASK.content);
      await expect(panelOf(page).getByText('Two have blocking')).toBeVisible();
      await expect(panelOf(page).getByRole('button', { name: 'Stop' })).toBeVisible();
    },
  },
  {
    name: 'answer-queue',
    scene: { base: 'queue', open: T_ANSWER, ...ALL_THREADS },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Queue' })).toBeVisible();
      await expect(panelOf(page).getByText('CP-1044 and CP-1050 have warnings only.')).toBeVisible();
    },
  },
  {
    name: 'answer-review-page',
    path: '/items/1',
    scene: { open: T_ANSWER, ...ALL_THREADS },
    ready: async (page) => {
      await expect(panelOf(page).getByText('CP-1044 and CP-1050 have warnings only.')).toBeVisible();
      await expect(panelOf(page).getByText('Context: CP-1')).toBeVisible();
      await page.waitForTimeout(600); // the review screen's own panes
    },
  },
  {
    name: 'approval-pending',
    scene: { base: 'queue', open: T_PENDING, ...ALL_THREADS },
    ready: async (page) => {
      await expect(cardOf(page)).toBeVisible();
    },
  },
  {
    name: 'approval-pending-review-page',
    path: '/items/1',
    scene: {},
    ready: async (page) => {
      await draftForApproval(page);
    },
  },
  {
    name: 'approval-edit',
    scene: { base: 'queue', open: T_PENDING, ...ALL_THREADS },
    ready: async (page) => {
      await cardOf(page).getByRole('button', { name: 'Edit' }).click();
      await expect(cardOf(page).getByRole('textbox', { name: 'To' })).toBeVisible();
    },
  },
  {
    name: 'approval-edit-422',
    scene: {
      interrupts: async (route, body) => {
        if ((body as { type?: string }).type !== 'edit') return route.fallback();
        const message = 'Not an internal address: marketing@lendfast.example';
        return json(
          route,
          { code: 'invalid_input', message, details: null, fields: [{ loc: ['body', 'to'], message }] },
          422,
        );
      },
    },
    ready: async (page) => {
      await draftForApproval(page);
      await cardOf(page).getByRole('button', { name: 'Edit' }).click();
      await cardOf(page)
        .getByRole('textbox', { name: 'To' })
        .fill('compliance@clearpath.demo, marketing@lendfast.example');
      await cardOf(page).getByRole('button', { name: 'Send edited' }).click();
      await expect(
        cardOf(page).getByText('Not an internal address: marketing@lendfast.example'),
      ).toBeVisible();
    },
  },
  {
    name: 'approval-reject',
    scene: {},
    ready: async (page) => {
      await draftForApproval(page);
      await cardOf(page).getByRole('button', { name: "Don't send" }).click();
      await expect(cardOf(page).getByRole('textbox', { name: 'Reason (optional)' })).toBeFocused();
    },
  },
  {
    name: 'sent',
    scene: {},
    ready: async (page) => {
      await draftForApproval(page);
      await cardOf(page).getByRole('button', { name: 'Send email' }).click();
      await expect(panelOf(page).getByText('Sent. It is in the Outbox.')).toBeVisible();
      await expect(panelOf(page).getByRole('link', { name: 'Open in Outbox' })).toBeVisible();
    },
  },
  {
    name: 'rejected',
    scene: { base: 'queue', open: T_REJECTED, ...ALL_THREADS },
    ready: async (page) => {
      await expect(panelOf(page).getByText('You declined this email')).toBeVisible();
    },
  },
  {
    name: 'refused',
    scene: { base: 'queue', open: T_REFUSED, ...ALL_THREADS },
    ready: async (page) => {
      await expect(
        panelOf(page).getByText("Blocked: marketing@lendfast.example isn't an internal address"),
      ).toBeVisible();
    },
  },
  {
    name: 'error-409',
    scene: {
      base: 'queue',
      open: T_ANSWER,
      ...ALL_THREADS,
      runs: (route) =>
        json(route, { code: 'conflict', message: 'A reply is already running in this thread.' }, 409),
    },
    ready: async (page) => {
      await expect(panelOf(page).getByText('CP-1044 and CP-1050 have warnings only.')).toBeVisible();
      await ask(page, 'Which of those are re-reviews?');
      await expect(panelOf(page).getByRole('alert')).toBeVisible();
    },
  },
  {
    name: 'error-failed',
    scene: {
      base: 'queue',
      open: T_ANSWER,
      ...ALL_THREADS,
      runs: (route, body) => {
        const { message } = body as { message: { id: string; content: string } };
        const human = { type: 'human', id: message.id, content: message.content };
        return route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseText([
            lifecycle('running'),
            values([...ANSWER_MESSAGES, human]),
            lifecycle('failed', 'The assistant hit its step limit on this question. Try a narrower one.'),
          ]),
        });
      },
    },
    ready: async (page) => {
      await expect(panelOf(page).getByText('CP-1044 and CP-1050 have warnings only.')).toBeVisible();
      await ask(page, 'Which of those are re-reviews?');
      await expect(panelOf(page).getByRole('alert')).toBeVisible();
    },
  },
  {
    name: 'outbox-empty',
    path: '/outbox',
    scene: { outbox: [] },
    ready: async (page) => {
      await expect(page.getByText('No emails yet')).toBeVisible();
    },
  },
  {
    name: 'outbox-loading',
    path: '/outbox',
    scene: { outbox: 'hang' },
    ready: async (page) => {
      await expect(page.getByRole('status', { name: 'Loading the outbox' })).toBeVisible();
    },
  },
  {
    name: 'outbox-error',
    path: '/outbox',
    scene: { outbox: 503 },
    ready: async (page) => {
      await expect(page.getByText("Couldn't load the outbox.")).toBeVisible({ timeout: 15_000 });
    },
  },
  {
    name: 'outbox-list',
    path: '/outbox',
    scene: { outbox: OUTBOX },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Sent emails' })).toBeVisible();
    },
  },
  {
    name: 'outbox-selected',
    path: '/outbox',
    scene: { outbox: OUTBOX },
    ready: async (page) => {
      await page.getByRole('button', { name: 'CP-1047 findings summary' }).click();
      await expect(page.getByTitle('Email preview')).toBeVisible();
    },
  },
  {
    name: 'outbox-selected-text',
    path: '/outbox',
    scene: { outbox: OUTBOX },
    ready: async (page) => {
      await page.getByRole('button', { name: 'Plain-text note: offer terms updated' }).click();
      await expect(page.getByText('Two approved items reference the old APR range.')).toBeVisible();
    },
  },
  {
    name: 'outbox-panel',
    path: '/outbox',
    scene: { outbox: OUTBOX, open: T_ANSWER, ...ALL_THREADS },
    ready: async (page) => {
      await expect(page.getByRole('table', { name: 'Sent emails' })).toBeVisible();
      await expect(panelOf(page).getByText('CP-1044 and CP-1050 have warnings only.')).toBeVisible();
    },
  },
  {
    name: 'outbox-panel-selected',
    path: '/outbox',
    scene: { outbox: OUTBOX, open: T_ANSWER, ...ALL_THREADS },
    ready: async (page) => {
      await page.getByRole('button', { name: /^Weekly re-review digest/ }).click();
      await expect(page.getByTitle('Email preview')).toBeVisible();
    },
  },
];

for (const size of SIZES) {
  for (const shot of shots) {
    test(`${shot.name} @ ${String(size.width)}`, async ({ page }) => {
      await page.setViewportSize(size);
      await setup(page, shot.scene);
      await page.goto(shot.path ?? '/');
      await shot.ready?.(page);
      await page.waitForTimeout(400); // let transitions (120ms) settle
      await page.screenshot({ path: `${OUT}/${shot.name}-${String(size.width)}.png` });
    });
  }

  // Keyboard and ARIA: records what happens (written to keyboard-<width>.json for the review) and captures
  // the focus states, rather than asserting the current behaviour.
  test(`keyboard @ ${String(size.width)}`, async ({ page }) => {
    await page.setViewportSize(size);
    await setup(page, {});
    await page.goto('/');
    const notes: Record<string, unknown> = {};
    const active = () =>
      page.evaluate(() => {
        const el = document.activeElement;
        if (el === null || el === document.body) return 'body';
        const name = el.getAttribute('aria-label') ?? (el.textContent || '').trim().slice(0, 40);
        const role = el.getAttribute('role');
        return `${el.tagName.toLowerCase()}${role === null ? '' : `[role=${role}]`} "${name}"`;
      });
    const mod = process.platform === 'darwin' ? 'Meta' : 'Control';
    const toggle = page.getByRole('button', { name: 'Assistant' });
    notes.toggleAttrs = {
      ariaExpanded: await toggle.getAttribute('aria-expanded'),
      ariaKeyshortcuts: await toggle.getAttribute('aria-keyshortcuts'),
    };

    await page.keyboard.press(`${mod}+Period`);
    await expect(panelOf(page)).toBeVisible();
    notes.afterShortcutOpen = await active();

    await page.keyboard.press('Escape');
    notes.escapeClosesPanel = !(await panelOf(page).isVisible());

    await page.keyboard.press(`${mod}+Period`);
    notes.afterShortcutClose = await active();
    notes.panelVisibleAfterShortcutClose = await panelOf(page).isVisible();

    // Reopen from the toggle with the keyboard and close with the Close button.
    await toggle.focus();
    await page.keyboard.press('Enter');
    notes.afterToggleOpen = await active();
    await panelOf(page).getByRole('button', { name: 'Close assistant' }).focus();
    await page.keyboard.press('Enter');
    notes.afterCloseButton = await active();

    // Tab order from the composer back through the panel header (Shift+Tab), and forward from the topbar toggle.
    await toggle.focus();
    await page.keyboard.press('Enter');
    const order: string[] = [];
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press('Shift+Tab');
      order.push(await active());
    }
    notes.shiftTabFromComposer = order;

    // Approval card: tab order and visible focus.
    await boxOf(page).focus();
    await ask(page, 'Email compliance a summary of CP-1');
    await expect(cardOf(page)).toBeVisible();
    notes.afterDraftArrives = await active();
    // Where the browser's sequential-focus starting point leaves a keyboard user once the composer locks.
    await page.keyboard.press('Tab');
    notes.tabAfterDraftArrives = await active();
    await page.keyboard.press('Shift+Tab');
    notes.thenShiftTab = await active();
    await cardOf(page).getByRole('link', { name: 'CP-1' }).focus();
    const cardOrder = [await active()];
    for (let i = 0; i < 5; i += 1) {
      await page.keyboard.press('Tab');
      cardOrder.push(await active());
    }
    notes.tabFromCardItemLink = cardOrder;
    await cardOf(page).getByRole('link', { name: 'CP-1' }).focus();
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/focus-approve-${String(size.width)}.png` });

    await cardOf(page).getByRole('button', { name: 'Edit' }).focus();
    await page.keyboard.press('Enter');
    notes.afterEditPressed = await active();
    await page.keyboard.press('Escape');
    notes.escapeInEditCancels = await cardOf(page).getByRole('button', { name: 'Send email' }).isVisible();
    await page.screenshot({ path: `${OUT}/focus-edit-${String(size.width)}.png` });

    notes.panelAria = await panelOf(page).ariaSnapshot();
    writeFileSync(`${OUT}/keyboard-${String(size.width)}.json`, `${JSON.stringify(notes, null, 2)}\n`);
  });
}
