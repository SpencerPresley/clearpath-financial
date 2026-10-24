/*
 * Step 1: each sheet column, a few of its values, and what it imports as (the server's guess, editable). Saving
 * sends every column (the server merges them) and returns the refreshed preview.
 */
import { useState } from 'react';

import { ImportTargetField } from '../../api/generated/model';
import type { ImportJobOut, ImportPreviewOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { SelectField } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { REQUIRED_TARGETS, TARGET_LABELS } from './labels';
import type { MappingErrors } from './mappingErrors';
import { useSaveMapping } from './useImportJob';

const TARGET_OPTIONS = Object.values(ImportTargetField).map((id) => ({ id, label: TARGET_LABELS[id] }));

export function ColumnsStep({
  job,
  onSaved,
  readOnly = false,
}: {
  job: ImportJobOut;
  onSaved: (preview: ImportPreviewOut) => void;
  /** A finished import: the mapping it used, as text. */
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState<Record<string, ImportTargetField>>(() =>
    Object.fromEntries(job.columns.map((c) => [c.name, c.field])),
  );
  const save = useSaveMapping(job.id, onSaved);
  const errors: MappingErrors = save.errors;

  const mapped = new Set(Object.values(draft));
  const missing = REQUIRED_TARGETS.filter((t) => !mapped.has(t));

  return (
    <div className="app-import-step">
      <header className="app-import-step-head">
        <h2 className="app-import-step-title">Columns</h2>
        <p className="app-import-step-detail">
          {readOnly
            ? 'What each column imported as.'
            : 'What each column imports as. Guesses come from the header; change any that are wrong, or choose Don’t import.'}
        </p>
      </header>
      <div className="app-import-panel">
        <table className="app-table app-import-table" aria-label="Column mapping">
          <colgroup>
            <col style={{ width: '18rem' }} />
            <col />
            <col style={{ width: '15rem' }} />
          </colgroup>
          <thead>
            <tr>
              <th className="app-th" scope="col">
                <span className="app-th-label">Column in the sheet</span>
              </th>
              <th className="app-th" scope="col">
                <span className="app-th-label">Sample values</span>
              </th>
              <th className="app-th" scope="col">
                <span className="app-th-label">Imports as</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {job.columns.map((column, index) => {
              const value = draft[column.name] ?? column.field;
              const changed = column.suggested_field !== null && value !== column.suggested_field;
              const error = errors.columns[index];
              return (
                <tr key={column.name} className="app-tr app-import-row">
                  <th scope="row" className="app-td app-import-colname">
                    {column.name}
                  </th>
                  <td className="app-td text-muted" title={column.sample_values.join(' · ')}>
                    {column.sample_values.length > 0 ? column.sample_values.join(', ') : 'Empty'}
                  </td>
                  <td className="app-td app-import-select">
                    {readOnly ? (
                      <span className="app-import-fixed">{TARGET_LABELS[value]}</span>
                    ) : (
                      <SelectField
                        label={`Imports as, ${column.name}`}
                        hideLabel
                        size="sm"
                        value={value}
                        options={TARGET_OPTIONS}
                        errorMessage={error ?? null}
                        description={
                          changed && column.suggested_field !== null
                            ? `Suggested: ${TARGET_LABELS[column.suggested_field]}`
                            : undefined
                        }
                        onChange={(next) => {
                          if (next !== null) setDraft((d) => ({ ...d, [column.name]: next }));
                        }}
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <footer className="app-import-actions app-import-actions-sticky">
          <Button
            variant="primary"
            isDisabled={save.isPending}
            onPress={() => {
              save.mutate({
                columns: job.columns.map((c) => ({ source: c.name, target: draft[c.name] ?? c.field })),
              });
            }}
          >
            {save.isPending ? 'Saving…' : 'Save and continue'}
          </Button>
          {errors.form !== null ? (
            <p className="app-import-error-text" role="alert">
              <Icon name="feedback.error" size={14} />
              {errors.form}
            </p>
          ) : (
            missing.length > 0 && (
              <p className="app-import-note">
                Not mapped yet: {missing.map((t) => TARGET_LABELS[t]).join(', ')}. Every row needs these to
                import.
              </p>
            )
          )}
        </footer>
      )}
    </div>
  );
}
