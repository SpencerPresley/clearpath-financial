/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import react from '@vitejs/plugin-react';
import { playwright } from '@vitest/browser-playwright';
import { defineConfig } from 'vite';

const BACKEND_URL = process.env.VITE_DEV_BACKEND_URL ?? 'http://localhost:8000';

export default defineConfig({
  // The router plugin must run before react() so route generation and code splitting work.
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react(), tailwindcss()],
  server: {
    // Same-origin in dev too: the browser only ever talks to Vite, which forwards API
    // and auth calls, so session cookies and CSRF behave as they do behind CloudFront.
    proxy: {
      '/api': { target: BACKEND_URL, changeOrigin: true },
      '/_allauth': { target: BACKEND_URL, changeOrigin: true },
    },
  },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'jsdom',
          setupFiles: ['vitest-canvas-mock', './src/test/setup.ts'],
          include: ['src/**/*.test.{ts,tsx}'],
          exclude: ['src/**/*.browser.test.{ts,tsx}'],
          // Vitest replaces CSS with "" by default; the contrast test reads theme.css?raw.
          css: { include: [/src\/theme\/theme\.css/] },
        },
      },
      {
        extends: true,
        test: {
          name: 'browser',
          include: ['src/**/*.browser.test.{ts,tsx}'],
          browser: {
            enabled: true,
            provider: playwright(),
            headless: true,
            screenshotFailures: false,
            instances: [{ browser: 'chromium' }],
          },
        },
      },
    ],
  },
});
