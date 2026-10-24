/*
 * Step 2: every distinct status, product, channel, partner, risk tier and trigger-terms value in the sheet, and
 * what it imports as. The importer's readings are filled in (the built-in tables, a partner matched under another
 * spelling), so the admin sees the mapping it inferred and can change any of it; values it doesn't recognize
 * (a status like "On Hold") wait for a choice. Shown on every import, not only when something is unmapped.
 *
 * Saving sends only what differs from the importer's own reading, plus the admin's earlier mappings: status values
 * go to `status_values`, the rest to `value_mappings`, and both lists replace what's saved. A value left unmapped
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
import type { ValueOption } from './labels';
import { useSaveMapping } from './useImportJob';

type Field = ImportValueField | 'status';
type Source = 'default' | 'matched' | 'mapped' | null;

interface ValueRow {
  key: string;
  field: Field;
  value: string;
  rows: number | null;
  /** What the server reads it as now (its tables, a matched spelling, or the saved mapping). */
  reading: string | null;
  source: Source;
  choice: string | null;
  /** Trigger terms "?": a known unknown, imported blank. Nothing to choose. */
  blank: boolean;
}

const FIELD_ORDER: readonly Field[] = [
  'status',
  'product',
  'channel',
  'partner',
  'risk_tier',
  'trigger_terms',
];
const VALUE_FIELDS = new Set<string>(FIELD_ORDER);

function isField(field: string): field is Field {
  return VALUE_FIELDS.has(field);
}

const SOURCE_LABELS: Record<Exclude<Source, null>, string> = {
  default: 'Built-in',
  matched: 'Matched spelling',
  mapped: 'Your mapping',
};

function rowsFrom(job: ImportJobOut, preview: ImportPreviewOut): ValueRow[] {
  const rows: ValueRow[] = [];
  const seen = new Set<string>();
  const add = (row: Omit<ValueRow, 'key' | 'choice'>) => {
    const key = `${row.field}:${row.value}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ ...row, key, choice: row.reading });
  };
  for (const s of job.status_values) {
    add({
      field: 'status',
      value: s.source_value,
      rows: s.rows,
      reading: s.status,
      source: s.source,
      blank: false,
    });
  }
  for (const v of job.values) {
    const blank = v.field === 'trigger_terms' && v.source === 'default' && v.value === null;
    add({ field: v.field, value: v.source_value, rows: v.rows, reading: v.value, source: v.source, blank });
  }
  for (const u of preview.unmapped) {
    if (isField(u.field))
      add({ field: u.field, value: u.value, rows: u.rows, reading: null, source: null, blank: false });
  }
  // Saved mappings for values no longer in the mapped column: listed (and kept) so saving doesn't drop them.
  for (const v of job.value_mappings) {
    add({
      field: v.field,
      value: v.source_value,
      rows: null,
      reading: v.value,
      source: 'mapped',
      blank: false,
    });
  }
  const unmappedFirst = (r: ValueRow) => (r.reading === null && !r.blank ? 0 : 1);
  return rows.sort(
    (a, b) =>
      FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field) || unmappedFirst(a) - unmappedFirst(b),
  );
}

/** Sent when it's the admin's: a change from the reading, or a mapping they saved before. */
function isOverride(row: ValueRow): boolean {
  return row.choice !== null && !row.blank && (row.source === 'mapped' || row.choice !== row.reading);
}

function optionsFor(row: ValueRow, partners: readonly string[]): ValueOption[] {
  const options = valueOptions(row.field, partners);
  // A partner only the workbook knows (created at commit) is still a valid reading.
  if (row.reading !== null && !options.some((o) => o.id === row.reading)) {
    options.push({ id: row.reading, label: row.reading });
  }
  return options;
}

function HowCell({ row }: { row: ValueRow }) {
  if (row.blank) return <span className="text-muted">Built-in</span>;
  if (row.choice === null) {
    return (
      <span className="app-import-how" data-unmapped="true">
        <Icon name="severity.warning" size={14} />
        Not mapped
      </span>
    );
  }
  const source = row.choice !== row.reading ? 'mapped' : row.source;
  return <span className="text-muted">{source === null ? '—' : SOURCE_LABELS[source]}</span>;
}

export function ValuesStep({
  job,
  preview,
  onSaved,
  readOnly = false,
}: {
  job: ImportJobOut;
  preview: ImportPreviewOut;
  onSaved: (preview: ImportPreviewOut) => void;
  /** A finished import: the values it used, as text. */
  readOnly?: boolean;
}) {
  const partners = useListPartners();
  const partnerNames = (partners.data ?? []).map((p) => p.name);
  const [rows, setRows] = useState<ValueRow[]>(() => rowsFrom(job, preview));
  const save = useSaveMapping(job.id, onSaved);

  // The lists in the order they're sent, so a 422's index lands back on its row.
  const statusRows = rows.filter((r) => r.field === 'status' && isOverride(r));
  const valueRows = rows.filter((r) => r.field !== 'status' && isOverride(r));
  const errorFor = (row: ValueRow): string | undefined => {
    const statusIndex = statusRows.indexOf(row);
    if (statusIndex !== -1) return save.errors.status_values[statusIndex];
    const valueIndex = valueRows.indexOf(row);
    return valueIndex === -1 ? undefined : save.errors.value_mappings[valueIndex];
  };
  const left = rows.filter((r) => r.choice === null && !r.blank);
  const leftRows = left.reduce((sum, r) => sum + (r.rows ?? 0), 0);
  const groups = FIELD_ORDER.map((field) => ({ field, rows: rows.filter((r) => r.field === field) })).filter(
    (g) => g.rows.length > 0,
  );

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
          {readOnly
            ? 'What each value in the sheet imported as.'
            : 'What each value in the sheet imports as. The importer’s readings are filled in; change any that are wrong. Unmapped values skip their rows.'}
        </p>
      </header>
      {rows.length === 0 ? (
        <div className="app-import-panel">
          <p className="app-import-empty">
            <Icon name="feedback.info" size={16} />
            No status, product, channel, partner, risk tier, or trigger-terms column is mapped.
          </p>
        </div>
      ) : (
        <div className="app-import-panel">
          <table className="app-table app-import-table" aria-label="Value mapping">
            <colgroup>
              <col />
              <col style={{ width: '7rem' }} />
              <col style={{ width: '16rem' }} />
              <col style={{ width: '10rem' }} />
            </colgroup>
            <thead>
              <tr>
                {['Value in the sheet', 'Rows', readOnly ? 'Imported as' : 'Imports as', 'From'].map((h) => (
                  <th key={h} className="app-th" scope="col">
                    <span className="app-th-label">{h}</span>
                  </th>
                ))}
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.field}>
                <tr className="app-import-group-row">
                  <th scope="rowgroup" colSpan={4} className="app-import-group-cell">
                    {VALUE_FIELD_LABELS[group.field]}
                    <span className="app-import-group-count">{plural(group.rows.length, 'value')}</span>
                  </th>
                </tr>
                {group.rows.map((row) => {
                  const options = optionsFor(row, partnerNames);
                  const error = errorFor(row);
                  const label = options.find((o) => o.id === row.choice)?.label ?? row.choice;
                  return (
                    <tr key={row.key} className="app-tr app-import-row">
                      <th scope="row" className="app-td app-import-colname">
                        “{row.value}”
                      </th>
                      <td className="app-td app-figure">
                        {row.rows === null ? '—' : plural(row.rows, 'row')}
                      </td>
                      <td className="app-td app-import-select">
                        {row.blank ? (
                          <span className="app-import-fixed text-muted">Unknown, left blank</span>
                        ) : readOnly ? (
                          <span className="app-import-fixed">{label ?? 'Not mapped'}</span>
                        ) : (
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
                        )}
                      </td>
                      <td className="app-td">
                        <HowCell row={row} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
        </div>
      )}
      {!readOnly && (
        <footer className="app-import-actions app-import-actions-sticky">
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
      )}
    </div>
  );
}
