/*
 * The review screen's URL (`/items/$itemId`, workstream I), for the drawer's plain <a href> so the link works
 * with a modifier key and in tests rendered without a router. In-app navigation uses the typed route
 * (QueuePage `navigate({ to: '/items/$itemId' })`).
 */
export function reviewPath(itemId: number): string {
  return `/items/${String(itemId)}`;
}
