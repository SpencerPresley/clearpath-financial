/*
 * Domain vocabulary the UI renders, mirrored from backend/core/domain.py.
 *
 * Temporary: the generated API client (src/api/generated) doesn't export these enums yet. When the
 * workstream-0 contract lands, re-export the generated types from here and delete the literals, so the
 * components keep importing from one place.
 */

export const ITEM_STATUSES = [
  'draft',
  'submitted',
  'in_review',
  'changes_requested',
  'approved',
  'rejected',
  'needs_rereview',
  'expired',
  'withdrawn',
] as const;
export type ItemStatus = (typeof ITEM_STATUSES)[number];

export const SEVERITIES = ['blocking', 'warning'] as const;
export type Severity = (typeof SEVERITIES)[number];

export const FINDING_SOURCES = ['code', 'llm', 'human'] as const;
export type FindingSource = (typeof FINDING_SOURCES)[number];

export const RISK_TIERS = ['high', 'medium', 'low'] as const;
export type RiskTier = (typeof RISK_TIERS)[number];

export const ROLES = ['marketer', 'reviewer', 'lead', 'admin'] as const;
export type Role = (typeof ROLES)[number];
