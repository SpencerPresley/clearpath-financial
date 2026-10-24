/*
 * The review screen's URL. Workstream I builds the `/items/$itemId` route; until it merges, the route isn't in
 * this branch's route tree, so typed <Link to> can't name it. Navigation goes through router.history with this
 * string. Swap to <Link to="/items/$itemId" params={{ itemId }}> once the route exists.
 */
export function reviewPath(itemId: number): string {
  return `/items/${String(itemId)}`;
}
