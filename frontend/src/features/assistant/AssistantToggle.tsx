/*
 * The topbar button for the assistant panel. A dot marks a draft waiting for your approval in any thread, so
 * a pending send stays visible with the panel closed. The shortcut is announced with aria-keyshortcuts, set on
 * the DOM node because React Aria's Button drops unknown attributes.
 */
import { useEffect } from 'react';
import type { RefObject } from 'react';
import { Button as AriaButton } from 'react-aria-components';

import { useListAssistantThreads } from '../../api/generated/assistant/assistant';
import { Icon } from '../../ui/Icon';
import { Kbd } from '../../ui/Kbd';
import { Tooltip } from '../../ui/Tooltip';
import { ASSISTANT_PANEL_ID } from './storage';

export const ASSISTANT_SHORTCUT = 'Meta+. Control+.';

function shortcutKeys(): string[] {
  return [/Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘' : 'Ctrl', '.'];
}

export function AssistantToggle({
  open,
  onPress,
  buttonRef,
}: {
  open: boolean;
  onPress: () => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
}) {
  useEffect(() => {
    buttonRef.current?.setAttribute('aria-keyshortcuts', ASSISTANT_SHORTCUT);
  }, [buttonRef]);
  const threads = useListAssistantThreads();
  const pending = (threads.data ?? []).some((thread) => thread.awaiting_approval);
  const label = pending ? 'Assistant, an email is waiting for your approval' : 'Assistant';

  return (
    <Tooltip
      content={
        <>
          {pending ? 'Assistant · email waiting for approval' : 'Assistant'} <Kbd keys={shortcutKeys()} />
        </>
      }
      placement="bottom"
    >
      <AriaButton
        ref={buttonRef}
        className="app-topbar-btn app-assistant-toggle"
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? ASSISTANT_PANEL_ID : undefined}
        data-active={open ? 'true' : undefined}
        onPress={onPress}
      >
        <Icon name="nav.assistant" size={18} />
        {pending && <span className="app-assistant-toggle-dot" aria-hidden="true" />}
      </AriaButton>
    </Tooltip>
  );
}
