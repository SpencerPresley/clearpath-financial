/**
 * After an in-app jump from the topbar (inbox row, quick-jump), put focus on the page, the skip link's target,
 * so it doesn't fall back to the topbar control. Leaves it alone if the new page already placed it inside
 * (a linked comment focuses itself).
 */
export function focusMain(): void {
  const main = document.getElementById('main');
  if (main !== null && !main.contains(document.activeElement)) main.focus();
}
