export interface KbdProps {
  /** One entry per key, in press order: ['Shift', 'A'], ['⌘', 'K']. */
  keys: readonly string[];
}

/** A keyboard shortcut. Nested <kbd> is the HTML idiom for a key combination. */
export function Kbd({ keys }: KbdProps) {
  return (
    <kbd className="app-kbd-group">
      {keys.map((key) => (
        <kbd key={key} className="app-kbd">
          {key}
        </kbd>
      ))}
    </kbd>
  );
}
