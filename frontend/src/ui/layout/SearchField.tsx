import { Input, SearchField as AriaSearchField } from 'react-aria-components';

import { Icon } from '../Icon';

/**
 * Global search placeholder. Disabled, and says so, until precedent search ships (workstream J); it
 * holds the topbar layout so nothing moves when it turns on.
 */
export function SearchField() {
  return (
    <AriaSearchField isDisabled aria-label="Search items" className="app-search">
      <Icon name="action.search" size={14} />
      <Input placeholder="Search isn't available yet" />
    </AriaSearchField>
  );
}
