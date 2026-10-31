import { defineConfig, devices } from '@playwright/test'

const record = !!process.env.RECORD
const baseURL = `http://127.0.0.1:${process.env.APP_PORT ?? 5173}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    ...(record && {
      viewport: { width: 1440, height: 900 },
      video: { mode: 'on', size: { width: 1440, height: 900 } },
      launchOptions: { slowMo: 400 },
    }),
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Playwright's bundled Chrome for Testing, not the headless shell.
        channel: 'chromium',
        ...(record && { viewport: { width: 1440, height: 900 } }),
      },
    },
  ],
  webServer: {
    command: 'bun run dev',
    // Through the Vite proxy, so this waits for both Vite and the API server.
    url: `${baseURL}/api/health`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
