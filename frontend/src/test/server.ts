import { setupServer } from 'msw/node';

import { getCoreMock } from '../api/generated/core/core.msw';
import { getDecisionsMock } from '../api/generated/decisions/decisions.msw';
import { getFindingsMock } from '../api/generated/findings/findings.msw';
import { getItemsMock } from '../api/generated/items/items.msw';
import { getMeMock } from '../api/generated/me/me.msw';
import { getPartnersMock } from '../api/generated/partners/partners.msw';
import { getUsersMock } from '../api/generated/users/users.msw';

// Default handlers come from the generated MSW mocks (faker data, random per call). Any test that asserts on
// data overrides with server.use(get<Op>MockHandler(fixture)).
export const server = setupServer(
  ...getCoreMock(),
  ...getMeMock(),
  ...getUsersMock(),
  ...getItemsMock(),
  ...getFindingsMock(),
  ...getDecisionsMock(),
  ...getPartnersMock(),
);
