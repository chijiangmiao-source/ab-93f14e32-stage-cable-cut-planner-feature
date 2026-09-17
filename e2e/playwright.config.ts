import { defineConfig } from '@playwright/test'

// Run against the Docker Compose stack by default (WEB_PORT 8080);
// override with WEB_URL, e.g. WEB_URL=http://localhost:5173 for the dev server.
export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: process.env.WEB_URL ?? 'http://localhost:8080',
  },
  reporter: [['list']],
})
