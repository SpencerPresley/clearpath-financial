import { Button as AriaButton, ListBox, ListBoxItem, Popover, Select } from 'react-aria-components';

import type { ItemRowOut, RiskTier } from '../../api/generated/model';
import { RISK_META, RiskTierBadge } from '../../ui/badges';
import { RISK_TIERS } from '../../ui/domain';
import { Icon } from '../../ui/Icon';
import { useQueueCell } from './cellContext';
import { stopRowClick } from './stopRowClick';

/** Risk tier: an inline picker for reviewers and leads (the server records an override event). */
export function RiskCell({ row }: { row: ItemRowOut }) {
  const { canEditRisk, save, activeId } = useQueueCell();
  if (!canEditRisk(row)) return <RiskTierBadge tier={row.risk_tier} short />;

  return (
    <span className="app-cell-control" onClick={stopRowClick}>
      <Select
        aria-label={`Risk tier for ${row.key}`}
        value={row.risk_tier}
        onChange={(key) => {
          if (key !== null && key !== row.risk_tier) save(row, { risk_tier: key as RiskTier });
        }}
      >
        <AriaButton className="app-cell-edit" excludeFromTabOrder={row.id !== activeId}>
          <RiskTierBadge tier={row.risk_tier} short />
          <Icon name="action.expand" size={12} className="app-cell-edit-caret" />
        </AriaButton>
        <Popover className="app-popover min-w-40" placement="bottom start" offset={4}>
          <ListBox className="app-menu">
            {RISK_TIERS.map((tier) => (
              <ListBoxItem
                key={tier}
                id={tier}
                textValue={RISK_META[tier].label}
                className="app-menu-item app-menu-check"
              >
                {({ isSelected }) => (
                  <>
                    <span className="app-menu-check-mark" aria-hidden="true">
                      {isSelected && <Icon name="action.approve" size={12} />}
                    </span>
                    <Icon name={RISK_META[tier].icon} size={14} />
                    {RISK_META[tier].label}
                  </>
                )}
              </ListBoxItem>
            ))}
          </ListBox>
        </Popover>
      </Select>
    </span>
  );
}
