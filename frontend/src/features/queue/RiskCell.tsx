import type { ItemRowOut } from '../../api/generated/model';
import { RiskTierBadge } from '../../ui/badges';

export function RiskCell({ row }: { row: ItemRowOut }) {
  return <RiskTierBadge tier={row.risk_tier} />;
}
