/*
 * A refused PUT /imports/{id}/mapping, sorted onto what the admin sees (spec §6.1: field 422s map to the field).
 * The server's locs index the lists we sent (["body", "value_mappings", 0, "value"]), so an indexed issue lands
 * on that row; anything else (a list-level issue, a 409) is the step's one-line message.
 */
import { apiErrorBody, apiErrorMessage } from '../../ui/forms/apiErrors';

type ListName = 'columns' | 'status_values' | 'value_mappings';

export interface MappingErrors {
  columns: Record<number, string>;
  status_values: Record<number, string>;
  value_mappings: Record<number, string>;
  form: string | null;
}

const LISTS: readonly ListName[] = ['columns', 'status_values', 'value_mappings'];

export function mappingErrors(error: unknown): MappingErrors {
  const out: MappingErrors = { columns: {}, status_values: {}, value_mappings: {}, form: null };
  const body = apiErrorBody(error);
  const loose: string[] = [];
  for (const issue of body?.fields ?? []) {
    const [, list, index] = issue.loc;
    const name = LISTS.find((l) => l === list);
    if (name !== undefined && typeof index === 'number') {
      out[name][index] ??= issue.message;
    } else {
      loose.push(issue.message);
    }
  }
  const placed = LISTS.some((l) => Object.keys(out[l]).length > 0);
  if (loose.length > 0) out.form = loose.join(' ');
  else if (!placed) out.form = apiErrorMessage(error);
  return out;
}

export const NO_ERRORS: MappingErrors = { columns: {}, status_values: {}, value_mappings: {}, form: null };
