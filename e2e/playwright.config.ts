import { fileURLToPath } from "node:url"

import { defineConfig } from "@playwright/test"

const repoRoot = fileURLToPath(new URL("..", import.meta.url))

export default defineConfig({
  testDir: "./tests",
  workers: 3,
  fullyParallel: true,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:5173/dash/",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `PORT=8888 MDDASH_DEMO_E2E=1 MDDASH_DEMO_ANALYSIS_CACHE="${repoRoot}e2e/fixtures/mdposit-cache" uv run --directory dashboard/api python _demo/app.py`,
      url: "http://localhost:8888/dash/api/health",
      timeout: 180_000,
      cwd: repoRoot,
    },
    {
      command: "pnpm --filter dash dev",
      url: "http://localhost:5173/dash/",
      timeout: 180_000,
      cwd: repoRoot,
    },
  ],
})
