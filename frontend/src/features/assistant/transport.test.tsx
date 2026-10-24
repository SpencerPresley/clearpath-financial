/*
 * The adapter under the real `useStream` controller, against MSW streaming SSE built from events recorded
 * from the Python agent (fixtures/wire.ts). These pin the behaviors the spike found the controller depends on:
 * thread-monotonic seq, replay to late subscribers, hydration of a pending interrupt, respond by id.
 */
import { HumanMessage } from '@langchain/core/messages';
import { useStream } from '@langchain/react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/mutator';
import { server } from '../../test/server';
import { assistantHandlers } from './fixtures/handlers';
import { EMPTY_STATE, lifecycle, textRun } from './fixtures/sse';
import { INTERRUPT_ID, RUN1, RUN2, STATE1, STATE2 } from './fixtures/wire';
import { AssistantTransport } from './transport';
import type { AssistantConfigurable, AssistantState, ToolApproval } from './types';

function renderStream(threadId = 't-1') {
  const transport = new AssistantTransport({ threadId });
  const loading: boolean[] = [];
  const hook = renderHook(() => {
    const stream = useStream<AssistantState, ToolApproval, AssistantConfigurable>({ transport, threadId });
    loading.push(stream.isLoading);
    return stream;
  });
  return { transport, loading, ...hook };
}

function texts(messages: readonly { type: string; text: string }[]) {
  return messages.map((m) => `${m.type}:${m.text}`);
}

describe('AssistantTransport under useStream', () => {
  it('streams a run to an approval interrupt, with the tool call finished and the item context sent', async () => {
    const { fake, handlers } = assistantHandlers({
      runs: [{ events: RUN1, state: STATE1, keepalive: true, burst: true }],
    });
    server.use(...handlers);
    const { result } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });

    await act(async () => {
      await result.current.submit(
        { messages: [new HumanMessage({ content: 'hi', id: 'u1' })] },
        { config: { configurable: { item_id: 7 } } },
      );
    });

    await waitFor(() => {
      expect(result.current.interrupts).toHaveLength(1);
    });
    expect(fake.posted).toEqual([
      { path: '/api/assistant/threads/t-1/runs', body: { message: { id: 'u1', content: 'hi' }, item_id: 7 } },
    ]);
    expect(result.current.interrupt?.id).toBe(INTERRUPT_ID);
    expect(result.current.interrupt?.value).toMatchObject({
      type: 'tool_approval',
      name: 'send_email',
      args: { to: ['a@clearpath.demo'], subject: 'S', body: 'B' },
    });
    expect(texts(result.current.messages)).toEqual([
      'human:hi',
      'ai:Let me search. ',
      'tool:CP-1: Loan ad',
      'ai:Drafting. ',
    ]);
    expect(result.current.toolCalls.map((t) => [t.name, t.status])).toContainEqual([
      'search_items',
      'finished',
    ]);
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it('resumes with the approval sent to the interrupt endpoint, then completes', async () => {
    const { fake, handlers } = assistantHandlers({
      runs: [
        { events: RUN1, state: STATE1 },
        { events: RUN2, state: STATE2 },
      ],
    });
    server.use(...handlers);
    const { result } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });
    await act(async () => {
      await result.current.submit({ messages: [new HumanMessage({ content: 'hi', id: 'u1' })] });
    });
    await waitFor(() => {
      expect(result.current.interrupts).toHaveLength(1);
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.respond({ type: 'approve' }, { interruptId: INTERRUPT_ID });
    });

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(6);
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(fake.posted[1]).toEqual({
      path: `/api/assistant/threads/t-1/interrupts/${INTERRUPT_ID}`,
      body: { type: 'approve' },
    });
    expect(result.current.interrupts).toHaveLength(0);
    expect(texts(result.current.messages).at(-1)).toBe('ai:Sent it. ');
  });

  it('hydrates a pending approval from GET state after a reload, and the response still reaches it', async () => {
    const { fake, handlers } = assistantHandlers({ runs: [{ events: RUN2, state: STATE2 }], state: STATE1 });
    server.use(...handlers);
    const { result } = renderStream();

    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });
    expect(result.current.messages).toHaveLength(4);
    expect(result.current.interrupt?.id).toBe(INTERRUPT_ID);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      await result.current.respond(
        { type: 'reject', message: 'Not yet' },
        { interruptId: result.current.interrupt?.id ?? '' },
      );
    });
    await waitFor(() => {
      expect(result.current.messages).toHaveLength(6);
    });
    expect(fake.posted).toEqual([
      {
        path: `/api/assistant/threads/t-1/interrupts/${INTERRUPT_ID}`,
        body: { type: 'reject', message: 'Not yet' },
      },
    ]);
  });

  it('hydrates a run cut short (next set, no approval) as idle, not loading forever', async () => {
    // What a Stop, a closed tab or a dropped connection leaves: the checkpoint of the last finished step.
    const human = { type: 'human', id: 'u1', content: 'hi' };
    const { handlers } = assistantHandlers({
      runs: [],
      state: { ...EMPTY_STATE, values: { messages: [human] }, next: ['model'], tasks: [] },
    });
    server.use(...handlers);
    const { result } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.isLoading).toBe(false);
    expect(texts(result.current.messages)).toEqual(['human:hi']);
  });

  it('surfaces a 409 from the run endpoint as stream.error with the API body', async () => {
    server.use(
      http.get('*/api/assistant/threads/:threadId/state', () => HttpResponse.json(EMPTY_STATE)),
      http.post('*/api/assistant/threads/:threadId/runs', () =>
        HttpResponse.json({ code: 'conflict', message: 'A reply is already running.' }, { status: 409 }),
      ),
    );
    const { result } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });

    await act(async () => {
      await result.current.submit({ messages: [new HumanMessage({ content: 'hi', id: 'u1' })] });
    });

    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(ApiError);
    });
    const error = result.current.error as ApiError;
    expect(error.status).toBe(409);
    expect(error.body).toMatchObject({ message: 'A reply is already running.' });
    expect(result.current.isLoading).toBe(false);
  });

  it('runs a second run on the same thread: loading goes true then false again (seq stays monotonic)', async () => {
    const first = textRun({ id: 'u1', content: 'one' }, { id: 'a1', text: 'First answer.' });
    const second = textRun(
      { id: 'u2', content: 'two' },
      { id: 'a2', text: 'Second answer.' },
      first.messages,
    );
    const { handlers } = assistantHandlers({
      runs: [
        { events: first.events, state: { ...EMPTY_STATE, values: { messages: first.messages } } },
        { events: second.events, state: { ...EMPTY_STATE, values: { messages: second.messages } } },
      ],
    });
    server.use(...handlers);
    const { result, loading } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });

    await act(async () => {
      await result.current.submit({ messages: [new HumanMessage({ content: 'one', id: 'u1' })] });
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(texts(result.current.messages)).toEqual(['human:one', 'ai:First answer.']);

    const before = loading.length;
    await act(async () => {
      await result.current.submit({ messages: [new HumanMessage({ content: 'two', id: 'u2' })] });
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(loading.slice(before)).toContain(true);
    expect(texts(result.current.messages)).toEqual([
      'human:one',
      'ai:First answer.',
      'human:two',
      'ai:Second answer.',
    ]);
  });

  it('turns a failed run into stream.error with the server line', async () => {
    const { handlers } = assistantHandlers({
      runs: [
        {
          events: [lifecycle('running'), lifecycle('failed', 'The model is unavailable.')],
          state: EMPTY_STATE,
        },
      ],
    });
    server.use(...handlers);
    const { result } = renderStream();
    await waitFor(() => {
      expect(result.current.isThreadLoading).toBe(false);
    });
    await act(async () => {
      await result.current.submit({ messages: [new HumanMessage({ content: 'hi', id: 'u1' })] });
    });
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(Error);
    });
    expect((result.current.error as Error).message).toBe('The model is unavailable.');
    expect(result.current.isLoading).toBe(false);
  });
});

describe('AssistantTransport', () => {
  it('answers commands it does not implement with not_supported', async () => {
    const transport = new AssistantTransport({ threadId: 't-1' });
    const response = await transport.send({
      id: 3,
      method: 'state.get',
      params: { namespace: [] },
    } as unknown as Parameters<AssistantTransport['send']>[0]);
    expect(response).toMatchObject({ type: 'error', id: 3, error: 'not_supported' });
  });

  it('replays the current run to a late subscriber, filtered by channel, with seq numbered across runs', async () => {
    const first = textRun({ id: 'u1', content: 'one' }, { id: 'a1', text: 'Hi.' });
    const { handlers } = assistantHandlers({
      runs: [
        { events: first.events, state: EMPTY_STATE },
        { events: [lifecycle('running'), lifecycle('completed')], state: EMPTY_STATE },
      ],
    });
    server.use(...handlers);
    const transport = new AssistantTransport({ threadId: 't-1' });
    const start = (id: number, text: string) =>
      transport.send({
        id,
        method: 'run.start',
        params: {
          assistant_id: '_',
          input: { messages: [{ type: 'human', content: text, id: `u${String(id)}` }] },
        },
      });

    const firstResponse = await start(1, 'one');
    expect(firstResponse).toMatchObject({ type: 'success', id: 1, meta: { applied_through_seq: 0 } });
    await waitFor(() => {
      expect(transport.bufferedCount).toBe(first.events.length);
    });

    const secondResponse = await start(2, 'two');
    expect(secondResponse).toMatchObject({ meta: { applied_through_seq: first.events.length } });
    await waitFor(() => {
      expect(transport.bufferedCount).toBe(2);
    });
    const handle = transport.openEventStream({ channels: ['lifecycle'] });
    const seen: { seq?: number; data: unknown }[] = [];
    for await (const message of handle.events) {
      const event = message as { seq?: number; params: { data: unknown } };
      seen.push({ seq: event.seq, data: event.params.data });
      if (seen.length === 2) break;
    }
    handle.close();
    expect(seen).toEqual([
      { seq: first.events.length + 1, data: { event: 'running' } },
      { seq: first.events.length + 2, data: { event: 'completed' } },
    ]);
  });
});
