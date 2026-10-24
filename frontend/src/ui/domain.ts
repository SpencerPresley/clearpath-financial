/*
 * Domain vocabulary the UI renders. The enums are the generated API contract (orval output from the backend's
 * core.domain), re-exported here so components keep one import path and nothing is hand-mirrored.
 */
import { FindingSource, ItemStatus, RiskTier, Role, Severity } from '../api/generated/model';

export { FindingSource, ItemStatus, RiskTier, Role, Severity };

export const ITEM_STATUSES: readonly ItemStatus[] = Object.values(ItemStatus);
export const SEVERITIES: readonly Severity[] = Object.values(Severity);
export const FINDING_SOURCES: readonly FindingSource[] = Object.values(FindingSource);
export const RISK_TIERS: readonly RiskTier[] = Object.values(RiskTier);
export const ROLES: readonly Role[] = Object.values(Role);
