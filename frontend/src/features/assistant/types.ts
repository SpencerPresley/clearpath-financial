/*
 * Types for the assistant stream. The HITL per-call payload has no exported JS type (spike finding 7), so it
 * is declared here; it matches the contract's ToolApprovalOut.
 */
import type { BaseMessage } from '@langchain/core/messages';

import type { ApproveIn, EditIn, RejectIn, ToolApprovalOut } from '../../api/generated/model';

export interface AssistantState {
  messages: BaseMessage[];
}

/** What `send_email` pauses on: one interrupt per gated call. */
export type ToolApproval = ToolApprovalOut;

export type ApprovalResponse = ApproveIn | EditIn | RejectIn;

/** `configurable` the panel passes on submit; the transport reads `item_id`. */
export interface AssistantConfigurable {
  item_id?: number;
}
