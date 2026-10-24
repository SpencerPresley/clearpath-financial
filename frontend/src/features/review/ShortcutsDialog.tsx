import { ModalDialog } from '../../ui/Dialog';
import { Kbd } from '../../ui/Kbd';

export const REVIEW_SHORTCUTS: readonly { keys: readonly string[]; label: string }[] = [
  { keys: ['N'], label: 'Next finding' },
  { keys: ['P'], label: 'Previous finding' },
  { keys: ['A'], label: 'Accept the selected finding' },
  { keys: ['D'], label: 'Dismiss the selected finding (asks for a reason)' },
  { keys: ['E'], label: 'Approve with edits (edit the copy)' },
  { keys: ['⇧', 'A'], label: 'Approve (opens the form; fast-track on a re-review)' },
  { keys: ['⇧', 'R'], label: 'Request changes (opens the form)' },
  { keys: ['⇧', 'X'], label: 'Reject (opens the form)' },
  { keys: ['⌘/Ctrl', 'Enter'], label: 'Submit the open decision (also from the editor)' },
  { keys: ['Esc'], label: 'Close the decision form or reason' },
  { keys: ['J'], label: 'Next item in your queue view' },
  { keys: ['?'], label: 'Show these shortcuts' },
];

export function ShortcutsDialog({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <ModalDialog title="Keyboard shortcuts" isOpen={isOpen} onOpenChange={onOpenChange}>
      <dl className="app-shortcuts">
        {REVIEW_SHORTCUTS.map((shortcut) => (
          <div key={shortcut.label} className="app-shortcut">
            <dt>
              <Kbd keys={shortcut.keys} />
            </dt>
            <dd>{shortcut.label}</dd>
          </div>
        ))}
      </dl>
      <p className="app-muted">Shortcuts are off while you type in a field.</p>
    </ModalDialog>
  );
}
