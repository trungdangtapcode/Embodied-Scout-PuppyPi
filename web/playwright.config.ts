import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:18766",
    viewport: { width: 1440, height: 1100 },
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      "cd .. && UV_PROJECT_ENVIRONMENT=.venv-dev uv run --locked --extra dev --extra app python scripts/mobile_browser_server.py",
    url: "http://127.0.0.1:18766/api/health",
    timeout: 30_000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
  },
});
