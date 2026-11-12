import { defineConfig, devices } from "@playwright/test";

// The E2E suite runs against a dedicated SQLite file so it never touches the demo database.
const E2E_DB = "sqlite:///./e2e.db";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5199", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        `cd ../backend && rm -f e2e.db && DATABASE_URL=${E2E_DB} uv run alembic upgrade head && ` +
        `DATABASE_URL=${E2E_DB} uv run python -m app.seed && ` +
        `DATABASE_URL=${E2E_DB} CORS_ORIGINS=http://localhost:5199 uv run uvicorn app.main:app --port 8099`,
      url: "http://localhost:8099/api/v1/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "API_URL=http://localhost:8099 pnpm vite --port 5199 --strictPort",
      url: "http://localhost:5199",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
