/*
 * Protocol events recorded from the real Python agent (create_agent + HITL per_call, astream_events v3,
 * translated to the wire format), trimmed: no additional_kwargs/response_metadata/timestamps. RUN1 searches,
 * drafts an email and ends interrupted on its approval; RUN2 is the approve resume. STATE1/STATE2 are
 * GET /state after each run. Wire events carry no seq/event_id: the transport assigns them. The send_email
 * tool message's artifact (`outcome`, `outbox_id`, `to`, `item_keys`) was added after recording, matching the
 * backend's current shape (backend/assistant/tools.py).
 */
import type { AssistantThreadStateOut } from '../../../api/generated/model';

export interface WireEvent {
  type: 'event';
  method: string;
  params: { namespace: string[]; data?: unknown; node?: string };
}

export const INTERRUPT_ID = '295f2fc41d7bfe377f257e367956ab74';

export const RUN1: WireEvent[] = [
  { type: 'event', method: 'lifecycle', params: { namespace: [], data: { event: 'running' } } },
  {
    type: 'event',
    method: 'values',
    params: { namespace: [], data: { messages: [{ content: 'hi', type: 'human', name: null, id: 'u1' }] } },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'message-start', role: 'ai', id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7' },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-start', index: 0, content: { type: 'text', text: '' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'Let ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'me ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'search. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: {
        event: 'content-block-start',
        index: 1,
        content: { type: 'tool_call', id: 'c1', name: 'search_items', args: {} },
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-finish', index: 0, content: { type: 'text', text: 'Let me search. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: {
        event: 'content-block-finish',
        index: 1,
        content: { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: { namespace: [], node: 'model', data: { event: 'message-finish' } },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'tools',
    params: {
      namespace: [],
      data: { event: 'tool-started', tool_call_id: 'c1', tool_name: 'search_items', input: { q: 'loan' } },
    },
  },
  {
    type: 'event',
    method: 'tools',
    params: {
      namespace: [],
      data: {
        event: 'tool-finished',
        tool_call_id: 'c1',
        output: {
          content: 'CP-1: Loan ad',
          type: 'tool',
          name: 'search_items',
          id: null,
          tool_call_id: 'c1',
          artifact: null,
          status: 'success',
        },
      },
    },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'message-start', role: 'ai', id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8' },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-start', index: 0, content: { type: 'text', text: '' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'Drafting. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: {
        event: 'content-block-start',
        index: 1,
        content: { type: 'tool_call', id: 'c2', name: 'send_email', args: {} },
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-finish', index: 0, content: { type: 'text', text: 'Drafting. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: {
        event: 'content-block-finish',
        index: 1,
        content: {
          type: 'tool_call',
          id: 'c2',
          name: 'send_email',
          args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
        },
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: { namespace: [], node: 'model', data: { event: 'message-finish' } },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
          {
            content: [
              { type: 'text', text: 'Drafting. ', index: 0 },
              {
                type: 'tool_call',
                id: 'c2',
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
              },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
            tool_calls: [
              {
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
                id: 'c2',
                type: 'tool_call',
              },
            ],
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
          {
            content: [
              { type: 'text', text: 'Drafting. ', index: 0 },
              {
                type: 'tool_call',
                id: 'c2',
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
              },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
            tool_calls: [
              {
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
                id: 'c2',
                type: 'tool_call',
              },
            ],
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'input.requested',
    params: {
      namespace: [],
      data: {
        interrupt_id: '295f2fc41d7bfe377f257e367956ab74',
        payload: {
          type: 'tool_approval',
          tool_call_id: 'c2',
          name: 'send_email',
          args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
          description: 'Tool execution requires approval\n\nTool: send_email',
        },
      },
    },
  },
  { type: 'event', method: 'lifecycle', params: { namespace: [], data: { event: 'interrupted' } } },
];

export const RUN2: WireEvent[] = [
  { type: 'event', method: 'lifecycle', params: { namespace: [], data: { event: 'running' } } },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
          {
            content: [
              { type: 'text', text: 'Drafting. ', index: 0 },
              {
                type: 'tool_call',
                id: 'c2',
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
              },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
            tool_calls: [
              {
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
                id: 'c2',
                type: 'tool_call',
              },
            ],
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'tools',
    params: {
      namespace: [],
      data: {
        event: 'tool-started',
        tool_call_id: 'c2',
        tool_name: 'send_email',
        input: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
      },
    },
  },
  {
    type: 'event',
    method: 'tools',
    params: {
      namespace: [],
      data: {
        event: 'tool-finished',
        tool_call_id: 'c2',
        output: {
          content: 'sent',
          type: 'tool',
          name: 'send_email',
          id: null,
          tool_call_id: 'c2',
          artifact: { outcome: 'sent', outbox_id: 1, to: ['a@clearpath.demo'], item_keys: [] },
          status: 'success',
        },
      },
    },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
          {
            content: [
              { type: 'text', text: 'Drafting. ', index: 0 },
              {
                type: 'tool_call',
                id: 'c2',
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
              },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
            tool_calls: [
              {
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
                id: 'c2',
                type: 'tool_call',
              },
            ],
          },
          {
            content: 'sent',
            type: 'tool',
            name: 'send_email',
            id: '98594fab-1c2f-4ff5-ab97-a3b16ea20540',
            tool_call_id: 'c2',
            artifact: { outcome: 'sent', outbox_id: 1, to: ['a@clearpath.demo'], item_keys: [] },
            status: 'success',
          },
        ],
      },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'message-start', role: 'ai', id: 'lc_run--01a16e95-366b-778d-935a-2f9866b36ef1' },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-start', index: 0, content: { type: 'text', text: '' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'Sent ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-delta', index: 0, delta: { type: 'text-delta', text: 'it. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: {
      namespace: [],
      node: 'model',
      data: { event: 'content-block-finish', index: 0, content: { type: 'text', text: 'Sent it. ' } },
    },
  },
  {
    type: 'event',
    method: 'messages',
    params: { namespace: [], node: 'model', data: { event: 'message-finish' } },
  },
  {
    type: 'event',
    method: 'values',
    params: {
      namespace: [],
      data: {
        messages: [
          { content: 'hi', type: 'human', name: null, id: 'u1' },
          {
            content: [
              { type: 'text', text: 'Let me search. ', index: 0 },
              { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
            tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
          },
          {
            content: 'CP-1: Loan ad',
            type: 'tool',
            name: 'search_items',
            id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
            tool_call_id: 'c1',
            artifact: null,
            status: 'success',
          },
          {
            content: [
              { type: 'text', text: 'Drafting. ', index: 0 },
              {
                type: 'tool_call',
                id: 'c2',
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
              },
            ],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
            tool_calls: [
              {
                name: 'send_email',
                args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
                id: 'c2',
                type: 'tool_call',
              },
            ],
          },
          {
            content: 'sent',
            type: 'tool',
            name: 'send_email',
            id: '98594fab-1c2f-4ff5-ab97-a3b16ea20540',
            tool_call_id: 'c2',
            artifact: { outcome: 'sent', outbox_id: 1, to: ['a@clearpath.demo'], item_keys: [] },
            status: 'success',
          },
          {
            content: [{ type: 'text', text: 'Sent it. ', index: 0 }],
            type: 'ai',
            name: null,
            id: 'lc_run--01a16e95-366b-778d-935a-2f9866b36ef1',
            tool_calls: [],
          },
        ],
      },
    },
  },
  { type: 'event', method: 'lifecycle', params: { namespace: [], data: { event: 'completed' } } },
];

export const STATE1 = {
  values: {
    messages: [
      { content: 'hi', type: 'human', name: null, id: 'u1' },
      {
        content: [
          { type: 'text', text: 'Let me search. ', index: 0 },
          { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
        ],
        type: 'ai',
        name: null,
        id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
        tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
      },
      {
        content: 'CP-1: Loan ad',
        type: 'tool',
        name: 'search_items',
        id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
        tool_call_id: 'c1',
        artifact: null,
        status: 'success',
      },
      {
        content: [
          { type: 'text', text: 'Drafting. ', index: 0 },
          {
            type: 'tool_call',
            id: 'c2',
            name: 'send_email',
            args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
          },
        ],
        type: 'ai',
        name: null,
        id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
        tool_calls: [
          {
            name: 'send_email',
            args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
            id: 'c2',
            type: 'tool_call',
          },
        ],
      },
    ],
  },
  next: ['tools'],
  tasks: [
    {
      id: '18f87535-2e04-03c3-31e2-93182ad08e9e',
      name: 'tools',
      interrupts: [
        {
          id: '295f2fc41d7bfe377f257e367956ab74',
          value: {
            type: 'tool_approval',
            tool_call_id: 'c2',
            name: 'send_email',
            args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
            description: 'Tool execution requires approval\n\nTool: send_email',
          },
        },
      ],
    },
  ],
  metadata: { step: 5 },
  checkpoint: { checkpoint_id: '1f1cfc1b-81e2-6142-8005-b3e30de7731c' },
  created_at: '2026-10-24T15:43:54.981610+00:00',
} as unknown as AssistantThreadStateOut;

export const STATE2 = {
  values: {
    messages: [
      { content: 'hi', type: 'human', name: null, id: 'u1' },
      {
        content: [
          { type: 'text', text: 'Let me search. ', index: 0 },
          { type: 'tool_call', id: 'c1', name: 'search_items', args: { q: 'loan' } },
        ],
        type: 'ai',
        name: null,
        id: 'lc_run--01a16e95-3660-76fb-bed2-5af1e832a5d7',
        tool_calls: [{ name: 'search_items', args: { q: 'loan' }, id: 'c1', type: 'tool_call' }],
      },
      {
        content: 'CP-1: Loan ad',
        type: 'tool',
        name: 'search_items',
        id: 'e2329741-d2b7-48c1-a3a0-793fe4d1bcfa',
        tool_call_id: 'c1',
        artifact: null,
        status: 'success',
      },
      {
        content: [
          { type: 'text', text: 'Drafting. ', index: 0 },
          {
            type: 'tool_call',
            id: 'c2',
            name: 'send_email',
            args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
          },
        ],
        type: 'ai',
        name: null,
        id: 'lc_run--01a16e95-3664-70a8-b583-7b15919f17c8',
        tool_calls: [
          {
            name: 'send_email',
            args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
            id: 'c2',
            type: 'tool_call',
          },
        ],
      },
      {
        content: 'sent',
        type: 'tool',
        name: 'send_email',
        id: '98594fab-1c2f-4ff5-ab97-a3b16ea20540',
        tool_call_id: 'c2',
        artifact: { outcome: 'sent', outbox_id: 1, to: ['a@clearpath.demo'], item_keys: [] },
        status: 'success',
      },
      {
        content: [{ type: 'text', text: 'Sent it. ', index: 0 }],
        type: 'ai',
        name: null,
        id: 'lc_run--01a16e95-366b-778d-935a-2f9866b36ef1',
        tool_calls: [],
      },
    ],
  },
  next: [],
  tasks: [],
  metadata: { step: 8 },
  checkpoint: { checkpoint_id: '1f1cfc1b-81f2-6aec-8008-ce44c7cf0f06' },
  created_at: '2026-10-24T15:43:54.988410+00:00',
} as unknown as AssistantThreadStateOut;
