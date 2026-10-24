/*
 * The two kinds of file on a submission (decisions.md, "Two kinds of file"): one optional mockup image
 * (uploaded as kind `creative`) and any number of evidence files, each tagged with what it is. Files are
 * queued here and uploaded after the item is created.
 */
import type { ReactNode } from 'react';
import { FileTrigger } from 'react-aria-components';

import { Button } from '../../ui/Button';
import { SelectField } from '../../ui/forms/fields';
import type { SelectFieldProps } from '../../ui/forms/fields';
import { IconButton } from '../../ui/IconButton';
import { ATTACHMENT_KIND_LABELS, formatBytes } from '../../ui/labels';
import { EVIDENCE_KINDS } from './submitForm';
import type { EvidenceKind, QueuedEvidence } from './submitForm';

const KIND_OPTIONS = EVIDENCE_KINDS.map((kind) => ({ id: kind, label: ATTACHMENT_KIND_LABELS[kind] }));

/** The compact kind select for one evidence row. */
export function EvidenceKindSelect({
  fileName,
  ...props
}: { fileName: string } & Pick<SelectFieldProps<EvidenceKind>, 'value' | 'onChange' | 'errorMessage'>) {
  return (
    <SelectField
      {...props}
      label={`Kind for ${fileName}`}
      hideLabel
      size="sm"
      className="app-file-kind"
      placeholder="Kind…"
      options={KIND_OPTIONS}
    />
  );
}

export function MockupPicker({
  value,
  onChange,
}: {
  value: File | null;
  onChange: (file: File | null) => void;
}) {
  return (
    <div className="app-field">
      <span className="app-field-label">Mockup</span>
      {value === null ? (
        <div className="app-file-empty">
          <FileTrigger
            acceptedFileTypes={['image/*']}
            onSelect={(files) => {
              onChange(files?.[0] ?? null);
            }}
          >
            <Button size="sm">Add mockup image</Button>
          </FileTrigger>
          <span className="app-field-description">Optional. How the ad looks where it runs.</span>
        </div>
      ) : (
        <ul className="app-file-list">
          <li className="app-file-row">
            <span className="app-file-name">{value.name}</span>
            <span className="app-file-size">{formatBytes(value.size)}</span>
            <IconButton
              icon="action.close"
              size="sm"
              aria-label={`Remove ${value.name}`}
              onPress={() => {
                onChange(null);
              }}
            />
          </li>
        </ul>
      )}
    </div>
  );
}

export interface EvidencePickerProps {
  value: readonly QueuedEvidence[];
  onChange: (next: QueuedEvidence[]) => void;
  /** The kind control for row `index` (a form field of its own, so its error lands on it). */
  renderKind: (index: number) => ReactNode;
}

export function EvidencePicker({ value, onChange, renderKind }: EvidencePickerProps) {
  return (
    <div className="app-field">
      <span className="app-field-label">Evidence</span>
      {value.length > 0 && (
        <ul className="app-file-list">
          {value.map((item, index) => (
            <li key={`${item.file.name}-${String(index)}`} className="app-file-row">
              <span className="app-file-name">{item.file.name}</span>
              <span className="app-file-size">{formatBytes(item.file.size)}</span>
              {renderKind(index)}
              <IconButton
                icon="action.close"
                size="sm"
                aria-label={`Remove ${item.file.name}`}
                onPress={() => {
                  onChange(value.filter((_, i) => i !== index));
                }}
              />
            </li>
          ))}
        </ul>
      )}
      <div className="app-file-empty">
        <FileTrigger
          allowsMultiple
          onSelect={(files) => {
            if (files === null) return;
            onChange([...value, ...Array.from(files, (file) => ({ file, kind: null }))]);
          }}
        >
          <Button size="sm">Add evidence files</Button>
        </FileTrigger>
        {value.length === 0 && (
          <span className="app-field-description">
            Optional. Rate sheets, substantiation, prescreen criteria.
          </span>
        )}
      </div>
    </div>
  );
}
