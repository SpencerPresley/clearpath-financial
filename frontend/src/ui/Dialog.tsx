import { Dialog, Heading, Modal, ModalOverlay } from 'react-aria-components';
import type { ReactNode } from 'react';

import { IconButton } from './IconButton';

export interface ModalDialogProps {
  title: string;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  children: ReactNode;
  /** alertdialog for confirmations of destructive actions (reject, pull); dialog otherwise. */
  role?: 'dialog' | 'alertdialog';
  /** Width class; default fits a short form. */
  size?: 'sm' | 'md';
}

/**
 * A modal with a title and close button. Use only for confirmations of destructive or irreversible
 * actions and for reference overlays (shortcut help), spec §5.7; everything else is inline.
 */
export function ModalDialog({
  title,
  isOpen,
  onOpenChange,
  children,
  role = 'dialog',
  size = 'sm',
}: ModalDialogProps) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable className="app-modal-overlay">
      <Modal className="app-modal" data-size={size}>
        <Dialog role={role} className="app-dialog">
          {({ close }) => (
            <>
              <div className="app-dialog-header">
                <Heading slot="title" className="app-dialog-title">
                  {title}
                </Heading>
                <IconButton
                  icon="action.close"
                  aria-label="Close"
                  size="sm"
                  tooltip={false}
                  onPress={close}
                />
              </div>
              {children}
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
