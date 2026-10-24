/*
 * One thread's conversation. Owns the transport and the `useStream` controller, and is keyed by thread id in
 * the panel, so switching threads mounts a fresh controller that hydrates from GET state (a pending approval
 * reappears after a reload) instead of re-binding one mid-run.
 */
import { HumanMessage } from '@langchain/core/messages';
import { useStream } from '@langchain/react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ApiError } from '../../api/mutator';
import { ApprovalCard } from './ApprovalCard';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { AssistantTransport } from './transport';
import type { ApprovalResponse, AssistantConfigurable, AssistantState, ToolApproval } from './types';

const UNREACHABLE = "Couldn't reach the assistant. Try again.";

/** One line for stream.error (spec §5.4); null when someone closer to the failure shows it. */
export function streamErrorLine(error: unknown): string | null {
  if (error === undefined || error === null) return null;
  if (error instanceof ApiError) {
    if (error.status === 422) return null; // the approval form maps it onto its fields
    const body = error.body as { message?: unknown } | null;
    return typeof body?.message === 'string' && body.message !== '' ? body.message : UNREACHABLE;
  }
  if (error instanceof TypeError) return UNREACHABLE;
  return error instanceof Error && error.message !== '' ? error.message : UNREACHABLE;
}

export interface ThreadViewProps {
  threadId: string;
  /** Review-screen context sent with each message. */
  itemId?: number;
  /** A first message typed before the thread existed; sent once hydration finishes. */
  pending?: string;
  onPendingSent?: () => void;
  /** A run ended (title, approval flag and the Outbox may have changed). */
  onSettled: () => void;
  autoFocus?: boolean;
  /** Shown instead of the conversation while it's empty. */
  empty: (pick: (text: string) => void) => ReactNode;
}

export function ThreadView({
  threadId,
  itemId,
  pending,
  onPendingSent,
  onSettled,
  autoFocus,
  empty,
}: ThreadViewProps) {
  const [transport] = useState(() => new AssistantTransport({ threadId }));
  const stream = useStream<AssistantState, ToolApproval, AssistantConfigurable>({
    transport,
    threadId,
    onCompleted: onSettled,
  });
  const [draft, setDraft] = useState<{ text: string } | undefined>(undefined);
  // A run you started in this view: an approval it ends on takes focus (a hydrated one doesn't).
  const [ranHere, setRanHere] = useState(false);
  const sentPending = useRef(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const lastText = stream.messages.at(-1)?.text.length ?? 0;

  // Follow the reply as it streams, and land on the approval card when it appears.
  useEffect(() => {
    const body = bodyRef.current;
    if (body !== null) body.scrollTop = body.scrollHeight;
  }, [stream.messages.length, lastText, stream.interrupt]);

  const send = (text: string) => {
    setRanHere(true);
    void stream.submit(
      { messages: [new HumanMessage({ id: crypto.randomUUID(), content: text })] },
      { config: { configurable: itemId === undefined ? {} : { item_id: itemId } } },
    );
  };

  useEffect(() => {
    if (pending === undefined || stream.isThreadLoading || sentPending.current) return;
    sentPending.current = true;
    send(pending);
    onPendingSent?.();
  });

  const interrupt = stream.interrupt;
  const approval = interrupt?.value?.type === 'tool_approval' ? interrupt.value : undefined;
  const interruptId = interrupt?.id;
  const errorLine = streamErrorLine(stream.error);

  let lockedReason: string | undefined;
  if (stream.isThreadLoading) lockedReason = 'Loading the thread…';
  else if (approval !== undefined) lockedReason = 'Approve, edit or reject the email first';

  const respond = async (response: ApprovalResponse) => {
    if (interruptId === undefined) return;
    // Always by id: after a reload the interrupt is hydrated, and respond() without one finds nothing.
    await stream.respond(response, { interruptId });
  };

  const isEmpty = stream.messages.length === 0 && !stream.isLoading && !stream.isThreadLoading;

  return (
    <>
      <div className="app-assistant-body" ref={bodyRef}>
        {isEmpty ? (
          empty((text) => {
            setDraft({ text });
          })
        ) : (
          <MessageList
            messages={stream.messages}
            isLoading={stream.isLoading}
            chipContext={{
              live: new Map(stream.toolCalls.map((call) => [call.callId, call.status])),
              awaitingCallId: approval?.tool_call_id,
              isLoading: stream.isLoading,
            }}
          >
            {approval !== undefined && interruptId !== undefined && (
              <ApprovalCard
                key={interruptId}
                approval={approval}
                onRespond={respond}
                focusOnMount={ranHere}
              />
            )}
          </MessageList>
        )}
        {stream.isThreadLoading && (
          <div className="app-assistant-thinking" role="status" aria-label="Loading the thread">
            <span className="app-skeleton" style={{ width: '70%' }} aria-hidden="true" />
            <span className="app-skeleton" style={{ width: '45%' }} aria-hidden="true" />
          </div>
        )}
      </div>
      {errorLine !== null && (
        <p className="app-assistant-error" role="alert">
          {errorLine}
        </p>
      )}
      <Composer
        onSend={send}
        onStop={() => {
          // Closing the stream cancels the run server-side; cancel: false keeps the SDK from calling a
          // runs/cancel endpoint we don't have.
          transport.abortRun();
          void stream.stop({ cancel: false });
        }}
        running={stream.isLoading}
        lockedReason={lockedReason}
        contextKey={itemId === undefined ? undefined : `CP-${String(itemId)}`}
        autoFocus={autoFocus}
        draft={draft}
      />
    </>
  );
}
