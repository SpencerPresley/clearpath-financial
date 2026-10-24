import { useId } from 'react';

import { cx } from '../cx';
import { segmentText } from './segments';
import type { SpanMark } from './segments';

const ZERO_WIDTH_SPACE = '\u200b';

export interface CopyEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** UTF-16 marks for `value` (pass `visibleMarks` output so stale spans never misplace). */
  marks: readonly SpanMark[];
  label: string;
  /** Hide the label visually (it's still the textarea's accessible name). */
  hideLabel?: boolean;
  placeholder?: string;
  description?: string;
  errorMessage?: string;
  autoFocus?: boolean;
  name?: string;
  className?: string;
}

/**
 * A textarea with flagged spans highlighted under the text. The backdrop and the textarea share one grid
 * cell and identical text metrics (`.app-copy`), so the backdrop's marks sit exactly under the typed
 * characters; the backdrop also sets the height, so the editor grows with the copy and never scrolls
 * internally (no scroll syncing).
 */
export function CopyEditor({
  value,
  onChange,
  marks,
  label,
  hideLabel = false,
  placeholder,
  description,
  errorMessage,
  autoFocus,
  name,
  className,
}: CopyEditorProps) {
  const id = useId();
  const descriptionId = `${id}-description`;
  const errorId = `${id}-error`;
  const describedBy = [description === undefined ? null : descriptionId, errorMessage ? errorId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cx('app-field', className)}>
      <label htmlFor={id} className={hideLabel ? 'sr-only' : 'app-field-label'}>
        {label}
      </label>
      <div className="app-copy-editor" data-invalid={errorMessage ? 'true' : undefined}>
        <div className="app-copy app-copy-backdrop" aria-hidden="true">
          {segmentText(value, marks).map((segment) => {
            const top = segment.marks[0];
            return top === undefined ? (
              <span key={segment.start}>{segment.text}</span>
            ) : (
              <mark
                key={segment.start}
                className="app-mark"
                data-severity={top.severity}
                data-source={top.source}
              >
                {segment.text}
              </mark>
            );
          })}
          {/* A trailing newline needs a character after it to take up a line. */}
          {ZERO_WIDTH_SPACE}
        </div>
        <textarea
          id={id}
          name={name}
          className="app-copy app-copy-input"
          value={value}
          placeholder={placeholder}
          spellCheck
          rows={1}
          // Only where the user just asked to edit (Approve with edits), so focus follows their action.
          autoFocus={autoFocus}
          aria-invalid={errorMessage ? true : undefined}
          aria-describedby={describedBy === '' ? undefined : describedBy}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      </div>
      {description !== undefined && (
        <p id={descriptionId} className="app-field-description">
          {description}
        </p>
      )}
      {errorMessage ? (
        <p id={errorId} className="app-field-error">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
