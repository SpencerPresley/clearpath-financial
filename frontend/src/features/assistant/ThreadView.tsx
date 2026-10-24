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
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { ApprovalCard } from './ApprovalCard';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { AssistantTransport } from './transport';
import type { ApprovalResponse, AssistantConfigurable, AssistantState, ToolApproval } from './types';

const UNREACHABLE = "Couldn't reach the assistant. Try again.";

/** One line for stream.error (spec §5.4): what happened and what to do; null when the approval form shows it. */
export function streamErrorLine(error: unknown): string | null {
  if (error === undefined || error === null) return null;
  if (error instanceof ApiError) {
    if (error.status === 422) return null; // the approval form maps it onto its fields
    const body = error.body as { message?: unknown } | null;
    const message = typeof body?.message === 'string' && body.message !== '' ? body.message : UNREACHABLE;
    // The run lock's 409 says what happened; add what to do unless the server already does.
    return error.status === 409 && /already running/i.test(message) && !/send again/i.test(message)
      ? `${message} Wait for it to finish, then send again.`
      : message;
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
  /** Why nothing can be sent on this server at all (no model key); the thread stays readable. */
  unavailable?: string;
}

export function ThreadView({
  threadId,
  itemId,
  pending,
  onPendingSent,
  onSettled,
  autoFocus,
  empty,
  unavailable,
}: ThreadViewProps) {
  const [transport] = useState(() => new AssistantTransport({ threadId }));
  const stream = useStream<AssistantState, ToolApproval, AssistantConfigurable>({
    transport,
    threadId,
    onCompleted: onSettled,
    // No SDK echo: a message the server refuses before the run starts (409, 404) must not sit in the log
    // looking sent. The view shows its own pending bubble until the server's copy arrives (same id).
    optimistic: false,
  });
  const [draft, setDraft] = useState<{ text: string } | undefined>(undefined);
  // A run you started in this view: an approval it ends on takes focus (a hydrated one doesn't).
  const [ranHere, setRanHere] = useState(false);
  const [outgoing, setOutgoing] = useState<{ id: string; text: string } | null>(null);
  /** Refused before the run started: the text is back in the box and Retry resends it. */
  const [unsent, setUnsent] = useState<string | null>(null);
  const sentPending = useRef(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const lastText = stream.messages.at(-1)?.text.length ?? 0;

  // Follow the reply as it streams, and land on the approval card when it appears.
  useEffect(() => {
    const body = bodyRef.current;
    if (body !== null) body.scrollTop = body.scrollHeight;
  }, [stream.messages.length, lastText, stream.interrupt]);

  const send = (text: string) => {
    const id = crypto.randomUUID();
    setRanHere(true);
    setOutgoing({ id, text });
    setUnsent(null);
    void stream.submit(
      { messages: [new HumanMessage({ id, content: text })] },
      {
        config: { configurable: itemId === undefined ? {} : { item_id: itemId } },
        onError: (error) => {
          // Before the stream (ApiError from the POST, or no network): nothing was sent. Give the text back.
          if (error instanceof ApiError || error instanceof TypeError) {
            setOutgoing(null);
            setUnsent(text);
            setDraft({ text });
          }
        },
      },
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

  // Without a model key no run can start, so that reason wins over the transient ones.
  let lockedReason = unavailable;
  if (lockedReason === undefined && stream.isThreadLoading) lockedReason = 'Loading the thread…';
  else if (lockedReason === undefined && approval !== undefined)
    lockedReason = 'Decide on the email draft first';

  const respond = async (response: ApprovalResponse) => {
    if (interruptId === undefined) return;
    // Always by id: after a reload the interrupt is hydrated, and respond() without one finds nothing.
    await stream.respond(response, { interruptId });
  };

  const pendingText =
    outgoing !== null && !stream.messages.some((message) => message.id === outgoing.id)
      ? outgoing.text
      : undefined;
  const isEmpty =
    stream.messages.length === 0 && pendingText === undefined && !stream.isLoading && !stream.isThreadLoading;

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
            outgoing={pendingText}
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
        <div className="app-assistant-error" role="alert">
          <Icon name="feedback.error" size={14} className="app-assistant-error-icon" />
          <p>{errorLine}</p>
          {unsent !== null && (
            <Button
              size="sm"
              onPress={() => {
                setDraft({ text: '' });
                send(unsent);
              }}
            >
              Retry
            </Button>
          )}
        </div>
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
