/*
 * Step 2: values the built-in tables don't know (a status like "On Hold", a partner spelled a new way). Status
 * values go to `status_values`; product, channel, risk tier, partner, and trigger terms to `value_mappings`.
 * Both lists replace what's saved, so earlier admin mappings are listed (and sent) too. A value left unmapped
 * isn't an error here: its rows are skipped at commit, and the preview says how many.
 */
import { useState } from 'react';

import { useListPartners } from '../../api/generated/partners/partners';
import type {
  ImportJobOut,
  ImportPreviewOut,
  ImportValueField,
  ItemStatus,
  StatusMappingIn,
  ValueMappingIn,
} from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { SelectField } from '../../ui/forms/fields';
import { Icon } from '../../ui/Icon';
import { plural } from '../../ui/labels';
import { VALUE_FIELD_LABELS, valueOptions } from './labels';
import { useSaveMapping } from './useImportJob';

type Field = ImportValueField | 'status';

interface ValueRow {
  key: string;
  field: Field;
  value: string;
  rows: number | null;
  choice: string | null;
}

const VALUE_FIELDS = new Set<string>(['product', 'channel', 'risk_tier', 'partner', 'trigger_terms']);

function isField(field: string): field is Field {
  return field === 'status' || VALUE_FIELDS.has(field);
}

function rowsFrom(job: ImportJobOut, preview: ImportPreviewOut): ValueRow[] {
  const rows: ValueRow[] = [];
  const seen = new Set<string>();
  const add = (row: ValueRow) => {
    if (seen.has(row.key)) return;
    seen.add(row.key);
    rows.push(row);
  };
  for (const u of preview.unmapped) {
    if (isField(u.field))
      add({ key: `${u.field}:${u.value}`, field: u.field, value: u.value, rows: u.rows, choice: null });
  }
  for (const s of job.status_values) {
    if (s.source === 'mapped' && s.status !== null) {
      add({
        key: `status:${s.source_value}`,
        field: 'status',
        value: s.source_value,
        rows: s.rows,
        choice: s.status,
      });
    }
  }
  for (const v of job.value_mappings) {
    add({
      key: `${v.field}:${v.source_value}`,
      field: v.field,
      value: v.source_value,
      rows: null,
      choice: v.value,
    });
  }
  return rows;
}

export function ValuesStep({
  job,
  preview,
  onSaved,
}: {
  job: ImportJobOut;
  preview: ImportPreviewOut;
  onSaved: (preview: ImportPreviewOut) => void;
}) {
  const partners = useListPartners();
  const partnerNames = (partners.data ?? []).map((p) => p.name);
  const [rows, setRows] = useState<ValueRow[]>(() => rowsFrom(job, preview));
  const save = useSaveMapping(job.id, onSaved);

  // The lists in the order they're sent, so a 422's index lands back on its row.
  const statusRows = rows.filter((r) => r.field === 'status' && r.choice !== null);
  const valueRows = rows.filter((r) => r.field !== 'status' && r.choice !== null);
  const errorFor = (row: ValueRow): string | undefined => {
    const statusIndex = statusRows.indexOf(row);
    if (statusIndex !== -1) return save.errors.status_values[statusIndex];
    const valueIndex = valueRows.indexOf(row);
    return valueIndex === -1 ? undefined : save.errors.value_mappings[valueIndex];
  };
  const left = rows.filter((r) => r.choice === null);
  const leftRows = left.reduce((sum, r) => sum + (r.rows ?? 0), 0);

  const submit = () => {
    const status_values: StatusMappingIn[] = statusRows.map((r) => ({
      source_value: r.value,
      status: r.choice as ItemStatus,
    }));
    const value_mappings: ValueMappingIn[] = valueRows.map((r) => ({
      field: r.field as ImportValueField,
      source_value: r.value,
      value: r.choice ?? '',
    }));
    save.mutate({ status_values, value_mappings });
  };

  return (
    <div className="app-import-step">
      <header className="app-import-step-head">
        <h2 className="app-import-step-title">Values</h2>
        <p className="app-import-step-detail">
          Values the importer doesn&apos;t recognize. Map each to what it means here; unmapped values skip
          their rows.
        </p>
      </header>
      {rows.length === 0 ? (
        <div className="app-import-panel">
          <p className="app-import-empty">
            <Icon name="feedback.info" size={16} />
            Every status, product, channel, risk tier, partner, and trigger-terms value has a mapping.
          </p>
        </div>
      ) : (
        <div className="app-import-panel">
          <table className="app-table app-import-table" aria-label="Values to map">
            <colgroup>
              <col style={{ width: '9rem' }} />
              <col />
              <col style={{ width: '6rem' }} />
              <col style={{ width: '16rem' }} />
            </colgroup>
            <thead>
              <tr>
                {['Field', 'Value in the sheet', 'Rows', 'Imports as'].map((h) => (
                  <th key={h} className="app-th" scope="col">
                    <span className="app-th-label">{h}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const options = valueOptions(row.field, partnerNames);
                const error = errorFor(row);
                return (
                  <tr key={row.key} className="app-tr app-import-row">
                    <td className="app-td text-muted">{VALUE_FIELD_LABELS[row.field]}</td>
                    <th scope="row" className="app-td app-import-colname">
                      “{row.value}”
                    </th>
                    <td className="app-td app-figure">{row.rows === null ? '—' : plural(row.rows, 'row')}</td>
                    <td className="app-td app-import-select">
                      <SelectField
                        label={`Imports as, ${VALUE_FIELD_LABELS[row.field]} “${row.value}”`}
                        hideLabel
                        size="sm"
                        placeholder="Not mapped"
                        value={row.choice}
                        options={options}
                        errorMessage={error ?? null}
                        onChange={(choice) => {
                          setRows((all) => all.map((r) => (r.key === row.key ? { ...r, choice } : r)));
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <footer className="app-import-actions">
        <Button variant="primary" isDisabled={save.isPending} onPress={submit}>
          {save.isPending ? 'Saving…' : 'Save and continue'}
        </Button>
        {save.errors.form !== null ? (
          <p className="app-import-error-text" role="alert">
            <Icon name="feedback.error" size={14} />
            {save.errors.form}
          </p>
        ) : (
          left.length > 0 && (
            <p className="app-import-note">
              {plural(left.length, 'value')} not mapped yet
              {leftRows > 0 ? `: ${plural(leftRows, 'row')} will be skipped` : ''}.
            </p>
          )
        )}
      </footer>
    </div>
  );
}
