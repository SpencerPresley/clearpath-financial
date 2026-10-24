/*
 * The conversation: your messages as plain text, the assistant's as Markdown with its tool calls listed
 * under the turn that made them. Tool messages aren't shown on their own; they finish their call's chip.
 */
import type { BaseMessage } from '@langchain/core/messages';
import { Link } from '@tanstack/react-router';
import type { ReactNode } from 'react';

import { Icon } from '../../ui/Icon';
import type { IconKey } from '../../ui/icons';
import { AssistantMarkdown } from './AssistantMarkdown';
import { chipFor } from './toolChips';
import type { CallInput, CallResult, ChipContext, ChipStatus, ToolChip } from './toolChips';

const STATUS_ICON: Partial<Record<ChipStatus, IconKey>> = {
  running: 'feedback.running',
  error: 'feedback.error',
  awaiting: 'feedback.awaiting',
  stopped: 'action.stop',
};
const STATUS_TEXT: Record<ChipStatus, string> = {
  running: 'running',
  finished: 'done',
  error: 'failed',
  awaiting: 'waiting for approval',
  stopped: 'stopped',
};

interface Fields {
  type?: string;
  id?: string;
  text?: string;
  tool_calls?: { id?: string; name: string; args: unknown }[];
  tool_call_id?: string;
  status?: string;
  artifact?: unknown;
}

function fieldsOf(message: BaseMessage): Fields {
  return message;
}

function callsOf(message: BaseMessage): CallInput[] {
  return (fieldsOf(message).tool_calls ?? [])
    .filter((call) => typeof call.id === 'string' && call.id !== '')
    .map((call) => ({ id: call.id ?? '', name: call.name, args: call.args }));
}

/** Tool results by tool_call_id, from the tool messages in the thread. */
export function resultsOf(messages: readonly BaseMessage[]): Map<string, CallResult> {
  const results = new Map<string, CallResult>();
  for (const message of messages) {
    const fields = fieldsOf(message);
    if (fields.type === 'tool' && typeof fields.tool_call_id === 'string') {
      results.set(fields.tool_call_id, {
        status: fields.status === 'error' ? 'error' : 'success',
        artifact: fields.artifact,
      });
    }
  }
  return results;
}

function itemIdOf(key: string): string {
  return key.replace(/^CP-/, '');
}

function ItemKeyLink({ itemKey }: { itemKey: string }) {
  return (
    <Link to="/items/$itemId" params={{ itemId: itemIdOf(itemKey) }} className="app-assistant-item-link">
      {itemKey}
    </Link>
  );
}

/** The label with any CP key in it as a link ("Read CP-1047": the read you most want to follow). */
function LabelWithKeys({ label }: { label: string }) {
  const parts = label.split(/(\bCP-\d+\b)/);
  return (
    <span>
      {parts.map((part, index) =>
        /^CP-\d+$/.test(part) ? <ItemKeyLink key={index} itemKey={part} /> : part,
      )}
    </span>
  );
}

function Chip({ chip }: { chip: ToolChip }) {
  const icon = chip.icon ?? STATUS_ICON[chip.status];
  const extraKeys = chip.itemKeys.filter((key) => !chip.label.includes(key));
  return (
    <li
      className="app-assistant-tool"
      data-status={chip.status}
      data-tone={chip.tone}
      data-outcome={chip.outcome}
      data-icon={icon === undefined ? undefined : 'true'}
    >
      {icon !== undefined && (
        <Icon name={icon} size={14} className={chip.status === 'running' ? 'app-spin' : undefined} />
      )}
      <LabelWithKeys label={chip.label} />
      {chip.outcome === undefined && chip.status !== 'awaiting' && chip.status !== 'stopped' && (
        <span className="sr-only">, {STATUS_TEXT[chip.status]}</span>
      )}
      {chip.outcome === 'sent' && chip.outboxId !== undefined && (
        <>
          <span aria-hidden="true">·</span>
          <Link to="/outbox" search={{ email: chip.outboxId }} className="app-assistant-chip-link">
            Open in Outbox
          </Link>
        </>
      )}
      {extraKeys.slice(0, 6).map((key) => (
        <ItemKeyLink key={key} itemKey={key} />
      ))}
      {extraKeys.length > 6 && <span className="app-muted">+{extraKeys.length - 6}</span>}
    </li>
  );
}

export function MessageList({
  messages,
  chipContext,
  isLoading,
  children,
}: {
  messages: readonly BaseMessage[];
  chipContext: Omit<ChipContext, 'results'>;
  isLoading: boolean;
  /** After the last message: the approval card, the pending line. */
  children?: ReactNode;
}) {
  const context: ChipContext = { ...chipContext, results: resultsOf(messages) };
  const last = messages.at(-1);
  const lastIsAi = last !== undefined && fieldsOf(last).type === 'ai';

  return (
    <div className="app-assistant-log" role="log" aria-label="Conversation" aria-busy={isLoading}>
      {messages.map((message, index) => {
        const fields = fieldsOf(message);
        const key = fields.id ?? `m${String(index)}`;
        if (fields.type === 'human') {
          return (
            <div key={key} className="app-assistant-msg" data-role="user">
              <span className="sr-only">You:</span>
              <p className="app-assistant-user-text">{message.text}</p>
            </div>
          );
        }
        if (fields.type !== 'ai') return null;
        const chips = callsOf(message).map((call) => chipFor(call, context));
        const streaming = isLoading && message === last;
        return (
          <div key={key} className="app-assistant-msg" data-role="assistant">
            <span className="sr-only">Assistant:</span>
            {message.text !== '' && <AssistantMarkdown source={message.text} />}
            {streaming && chips.length === 0 && <span className="app-assistant-caret" aria-hidden="true" />}
            {chips.length > 0 && (
              <ul className="app-assistant-tools" aria-label="Tool calls">
                {chips.map((chip) => (
                  <Chip key={chip.id} chip={chip} />
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {isLoading && !lastIsAi && (
        <div className="app-assistant-msg app-assistant-thinking" data-role="assistant">
          <span className="app-skeleton" style={{ width: '60%' }} aria-hidden="true" />
          <span className="app-skeleton" style={{ width: '40%' }} aria-hidden="true" />
          <span className="sr-only">The assistant is replying</span>
        </div>
      )}
      {children}
    </div>
  );
}
