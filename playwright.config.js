const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/ui',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 -u -m artificial_ecology.demo',
    url: 'http://127.0.0.1:8000',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
