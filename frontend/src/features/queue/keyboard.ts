/*
 * Queue keyboard model (spec §4.3 Review: navigate the queue and open an item without the mouse). A pure
 * mapping from a key event to an action, so the rules are tested without a DOM layout; QueuePage applies it.
 *
 * Typing always wins: nothing fires from text fields, comboboxes, open menus, or modal dialogs. Enter and x
 * are left to buttons, links, and checkboxes, which already activate on them.
 */
export type QueueKeyAction = 'next' | 'prev' | 'open' | 'review' | 'select' | 'help' | 'close';

export interface KeyInput {
  key: string;
  target: EventTarget | null;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
}

const EDITABLE = [
  'input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit])',
  'textarea',
  'select',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[role=textbox]',
  '[role=combobox]',
  '[role=searchbox]',
  '[role=menu]',
  '[role=listbox]',
  '[role=dialog]',
  '[role=alertdialog]',
].join(',');

const ACTIVATES_ITSELF = 'button, a[href], input, [role=button], [role=link], [role=checkbox], [role=switch]';

const KEYS: Record<string, QueueKeyAction> = {
  j: 'next',
  ArrowDown: 'next',
  k: 'prev',
  ArrowUp: 'prev',
  Enter: 'open',
  o: 'review',
  x: 'select',
  '?': 'help',
  Escape: 'close',
};

export function queueKeyAction(e: KeyInput): QueueKeyAction | null {
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  const action = KEYS[e.key];
  if (action === undefined) return null;
  const target = e.target instanceof Element ? e.target : null;
  if (target?.closest(EDITABLE)) return null;
  if ((action === 'open' || action === 'select') && target?.closest(ACTIVATES_ITSELF)) return null;
  return action;
}

export const SHORTCUTS: readonly { keys: readonly string[]; label: string }[] = [
  { keys: ['j'], label: 'Next item (or ↓)' },
  { keys: ['k'], label: 'Previous item (or ↑)' },
  { keys: ['Enter'], label: 'Preview the item' },
  { keys: ['o'], label: 'Open review' },
  { keys: ['x'], label: 'Select or deselect' },
  { keys: ['?'], label: 'Show shortcuts' },
  { keys: ['Esc'], label: 'Close the preview' },
];
