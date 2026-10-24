/*
 * Notes in the table: the first line as text, or for the submitter and reviewers a button that opens a small
 * editor. Save is explicit (notes are prose, so Enter is a newline); the change shows at once and rolls back on
 * error, like every inline edit (useItemPatch).
 */
import { useState } from 'react';
import {
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Popover,
  TextArea,
  TextField,
} from 'react-aria-components';

import type { ItemRowOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { useQueueCell } from './cellContext';
import { stopRowClick } from './stopRowClick';

/** The API's limit (ItemUpdateIn.notes). */
export const NOTES_MAX = 10_000;

function firstLine(notes: string): string {
  return notes.split('\n').find((line) => line.trim() !== '') ?? '';
}

function NotesEditor({
  row,
  onSave,
  close,
}: {
  row: ItemRowOut;
  onSave: (notes: string) => void;
  close: () => void;
}) {
  const [value, setValue] = useState(row.notes);
  return (
    <div className="flex flex-col gap-2">
      <TextField
        aria-label={`Notes for ${row.key}`}
        value={value}
        onChange={setValue}
        maxLength={NOTES_MAX}
        autoFocus
      >
        <TextArea className="app-textarea" rows={4} placeholder="Visible to reviewers and the submitter" />
      </TextField>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onPress={close}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="primary"
          aria-label="Save notes"
          onPress={() => {
            if (value !== row.notes) onSave(value);
            close();
          }}
        >
          Save
        </Button>
      </div>
    </div>
  );
}

export function NotesCell({ row }: { row: ItemRowOut }) {
  const { canEditNotes, save, activeId } = useQueueCell();
  const line = firstLine(row.notes);
  if (!canEditNotes(row)) {
    return line === '' ? null : (
      <span className="app-cell-title" title={row.notes}>
        {line}
      </span>
    );
  }
  return (
    <span className="app-cell-control" onClick={stopRowClick}>
      <DialogTrigger>
        <AriaButton
          className="app-cell-edit app-cell-edit-wide"
          aria-label={`Notes for ${row.key}: ${line === '' ? 'none' : line}. Edit`}
          excludeFromTabOrder={row.id !== activeId}
        >
          {line === '' ? (
            <span className="app-cell-edit-hint">Add note</span>
          ) : (
            <span className="app-cell-title" title={row.notes}>
              {line}
            </span>
          )}
        </AriaButton>
        <Popover className="app-popover w-80 p-2" placement="bottom start" offset={4}>
          <Dialog aria-label={`Notes for ${row.key}`} className="outline-none">
            {({ close }) => (
              <NotesEditor
                row={row}
                close={close}
                onSave={(notes) => {
                  save(row, { notes });
                }}
              />
            )}
          </Dialog>
        </Popover>
      </DialogTrigger>
    </span>
  );
}
