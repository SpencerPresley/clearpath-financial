import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './server';

// jsdom has no layout, so no scrollIntoView; the queue calls it when j/k moves the active row.
Element.prototype.scrollIntoView = function scrollIntoView() {
  /* no layout in jsdom */
};

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});
