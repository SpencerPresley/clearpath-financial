import { setupServer } from 'msw/node';

import { getListAssistantThreadsMockHandler } from '../api/generated/assistant/assistant.msw';
import { getCoreMock } from '../api/generated/core/core.msw';
import { getListNotificationsMockHandler } from '../api/generated/notifications/notifications.msw';

// Default handlers come from the generated MSW mocks; tests override per case with
// server.use(...). The shell's assistant toggle lists threads and its bell polls notifications on every page
// (none of either by default).
export const server = setupServer(
  ...getCoreMock(),
  getListAssistantThreadsMockHandler([]),
  getListNotificationsMockHandler({ rows: [], unread_count: 0 }),
);
