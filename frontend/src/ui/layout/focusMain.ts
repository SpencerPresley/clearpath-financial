/**
 * After an in-app jump from the topbar (inbox row, quick-jump), put focus on the page, the skip link's target,
 * so it doesn't fall back to the topbar control. Only if focus is still where the jump left it: on the body, or
 * back on `leftFrom` (the control the jump came from, where a closing popover restores it). Anything else was
 * placed since, by the new page (a linked comment focuses itself) or by the user (⌘K right after a jump), and
 * stays.
 */
export function focusMain(leftFrom?: Element | null): void {
  const main = document.getElementById('main');
  const active = document.activeElement;
  const untouched = active === null || active === document.body || (leftFrom?.contains(active) ?? false);
  if (main !== null && untouched) main.focus();
}
