import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

import { noRawPaletteRule } from './src/theme/noRawPalette.ts';

const ICON_IMPORT_MESSAGE = 'Use <Icon name="..."> from src/ui/Icon (registry: src/ui/icons.ts).';

export default defineConfig([
  globalIgnores(['dist', 'src/api/generated', 'src/routeTree.gen.ts', 'playwright-report', 'test-results']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat['recommended-latest'],
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // React Query mutations and router navigation return promises; dropping one
      // silently swallows its error.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
    },
  },
  {
    // Spec §5.2a: one registry maps meanings to glyphs, so every icon import goes through it.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/ui/icons.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['@phosphor-icons/*', '@phosphor-icons/react/*'], message: ICON_IMPORT_MESSAGE },
          ],
        },
      ],
    },
  },
  {
    // theme.css resets the palette, radii, and shadows; raw utilities render nothing, so fail instead.
    files: ['src/**/*.tsx'],
    plugins: { clearpath: { rules: { 'no-raw-palette': noRawPaletteRule } } },
    rules: { 'clearpath/no-raw-palette': 'error' },
  },
]);
