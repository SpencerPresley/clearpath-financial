import { Dialog, Heading, Modal, ModalOverlay } from 'react-aria-components';

import { IconButton } from '../../ui/IconButton';
import { Kbd } from '../../ui/Kbd';
import { SHORTCUTS } from './keyboard';

/** Shortcuts help, opened with ? or the keyboard button. A modal, so j/k don't fire behind it. */
export function ShortcutsDialog({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable className="app-modal-overlay">
      <Modal className="app-modal w-80">
        <Dialog className="outline-none" aria-label="Keyboard shortcuts">
          {({ close }) => (
            <>
              <div className="app-modal-head">
                <Heading slot="title" className="text-sm font-semibold">
                  Keyboard shortcuts
                </Heading>
                <IconButton icon="action.close" size="sm" aria-label="Close" onPress={close} />
              </div>
              <dl className="app-shortcuts">
                {SHORTCUTS.map((s) => (
                  <div key={s.label} className="app-shortcut">
                    <dt>
                      <Kbd keys={s.keys} />
                    </dt>
                    <dd>{s.label}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
