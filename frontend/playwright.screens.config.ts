import { defineConfig } from "@playwright/test";

// Captures portfolio screenshots from a freshly seeded, isolated database (never the demo DB).
const DB = "sqlite:///./screens.db";

export default defineConfig({
  testDir: "./screens",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5197", colorScheme: "light", locale: "en-GB", timezoneId: "Asia/Jakarta" },
  webServer: [
    {
      command:
        `cd ../backend && rm -f screens.db && DATABASE_URL=${DB} uv run alembic upgrade head && ` +
        `DATABASE_URL=${DB} uv run python -m app.seed && ` +
        `DATABASE_URL=${DB} CORS_ORIGINS=http://localhost:5197 uv run uvicorn app.main:app --port 8097`,
      url: "http://localhost:8097/api/v1/health", reuseExistingServer: false, timeout: 120_000,
    },
    { command: "API_URL=http://localhost:8097 pnpm vite --port 5197 --strictPort", url: "http://localhost:5197", reuseExistingServer: false, timeout: 60_000 },
  ],
});
