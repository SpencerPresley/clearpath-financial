/*
 * Message box: Enter sends, Shift+Enter is a newline. Locked while a reply runs (Stop instead of Send) and
 * while an email waits for approval, so there is never a second run racing the first on one thread.
 */
import { useEffect, useRef, useState } from 'react';
import { Label, TextArea, TextField } from 'react-aria-components';

import { Button } from '../../ui/Button';

export interface ComposerProps {
  onSend: (text: string) => void;
  onStop?: () => void;
  /** A reply is streaming. */
  running: boolean;
  /** Why typing is locked right now, if it is (an approval is pending, the thread is loading). */
  lockedReason?: string;
  /** "CP-1042" when the panel is open on a review screen. */
  contextKey?: string;
  autoFocus?: boolean;
  /** Text to put in the box (an example ask); a new object each time so the same ask can be re-picked. */
  draft?: { text: string };
}

export function Composer({
  onSend,
  onStop,
  running,
  lockedReason,
  contextKey,
  autoFocus,
  draft,
}: ComposerProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const locked = running || lockedReason !== undefined;
  const canSend = !locked && text.trim() !== '';

  // An example ask picked from the empty state replaces the text (adjusting state while rendering, not in an
  // effect), then takes focus so Enter sends it.
  const [shownDraft, setShownDraft] = useState(draft);
  if (draft !== shownDraft) {
    setShownDraft(draft);
    if (draft !== undefined) setText(draft.text);
  }
  useEffect(() => {
    if (draft !== undefined) inputRef.current?.focus();
  }, [draft]);

  const send = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText('');
  };

  return (
    <form
      className="app-assistant-composer"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <TextField
        value={text}
        onChange={setText}
        isDisabled={locked}
        aria-describedby={lockedReason === undefined ? undefined : 'assistant-composer-locked'}
        className="app-assistant-composer-field"
      >
        <Label className="sr-only">Message the assistant</Label>
        <TextArea
          ref={inputRef}
          rows={3}
          // The panel was just opened by the user, so focus follows their action.
          autoFocus={autoFocus}
          className="app-assistant-composer-input"
          placeholder={lockedReason ?? 'Ask about items, findings, precedents…'}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
        />
      </TextField>
      <div className="app-assistant-composer-bar">
        {contextKey !== undefined ? (
          <span className="app-assistant-context">Context: {contextKey}</span>
        ) : (
          <span />
        )}
        {lockedReason !== undefined && !running && (
          <span id="assistant-composer-locked" className="sr-only">
            {lockedReason}
          </span>
        )}
        {running ? (
          <Button size="sm" icon="action.stop" onPress={onStop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" size="sm" variant="primary" isDisabled={!canSend}>
            Send
          </Button>
        )}
      </div>
    </form>
  );
}
