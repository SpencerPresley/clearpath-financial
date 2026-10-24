// Codegen from the backend's OpenAPI schema (openapi/ninja.json). Two outputs over
// the same input: TanStack Query hooks + TS models + MSW handlers, and zod schemas
// as sibling .zod.ts files. Everything under src/api/generated is overwritten by
// `npm run generate:api`; never hand-edit it.
import { defineConfig } from 'orval';

export default defineConfig({
  clearpath: {
    input: { target: './openapi/ninja.json' },
    output: {
      mode: 'tags-split',
      client: 'react-query',
      target: './src/api/generated',
      schemas: './src/api/generated/model',
      clean: true,
      mock: { generators: [{ type: 'msw', delay: false }] },
      override: {
        mutator: { path: './src/api/mutator.ts', name: 'customFetch' },
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
  clearpathZod: {
    input: { target: './openapi/ninja.json' },
    output: {
      mode: 'tags-split',
      client: 'zod',
      target: './src/api/generated',
      fileExtension: '.zod.ts',
    },
  },
});
