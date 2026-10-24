import { setupServer } from 'msw/node';

import { getListAssistantThreadsMockHandler } from '../api/generated/assistant/assistant.msw';
import { getCoreMock } from '../api/generated/core/core.msw';

// Default handlers come from the generated MSW mocks; tests override per case with
// server.use(...). The shell's assistant toggle lists threads on every page (no threads by default).
export const server = setupServer(...getCoreMock(), getListAssistantThreadsMockHandler([]));
