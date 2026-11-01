import { defineConfig, devices } from "@playwright/test";

/** E2E tests run against a live stack (API with demo data + Next.js). See docs/SETUP.md.
 *  We sign in once (auth.setup.ts) and reuse the session: the API rate-limits logins (10/min). */
const AUTH = "e2e/.auth/state.json";
export default defineConfig({
  testDir: "./e2e",
  outputDir: process.env.E2E_OUTPUT ?? "/tmp/1finance-e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    { name: "anonymous", testMatch: /auth\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "desktop", testMatch: /app\.spec\.ts/, dependencies: ["setup"], use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, storageState: AUTH } },
    { name: "mobile", testMatch: /app\.spec\.ts/, grep: /@responsive/, dependencies: ["setup"], use: { ...devices["Pixel 7"], storageState: AUTH } },
  ],
});
