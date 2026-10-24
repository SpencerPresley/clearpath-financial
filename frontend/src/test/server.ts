import { setupServer } from 'msw/node';

import { getCoreMock } from '../api/generated/core/core.msw';

// Default handlers come from the generated MSW mocks; tests override per case with
// server.use(...).
export const server = setupServer(...getCoreMock());
