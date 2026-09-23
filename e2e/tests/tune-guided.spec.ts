import { expect, test } from "@playwright/test"

// Seed: membrane study aaaaa, tuner job demo-tuner-membrane running forever with
// rolling trials (membrane_00000 FINISHED, membrane_00001 ERROR, membrane_00002 RUNNING).
// Run submission goes through the per-poll E2E schedule: ~3 polls to FINISHED.
test("guided tuning: trials, failed-trial logs, stop, and run submission", async ({ page }) => {
  await page.goto("experiments/aaaaa")
  await page.getByRole("button", { name: /Go to section 2: Tune/ }).click()
  await expect(page.getByRole("status", { name: "Tuning in progress" })).toBeVisible()

  await expect(page.getByRole("radio", { name: "Pick configuration membrane_00000" })).toBeEnabled()
  await expect(page.getByRole("radio", { name: "Pick configuration membrane_00002" })).toBeDisabled()

  await page.getByRole("button", { name: "View output of failed trial membrane_00001" }).click()
  await expect(page.getByRole("dialog").getByText("Trial output")).toBeVisible()
  await page.getByRole("tab", { name: "Standard error" }).click()
  await page.getByRole("button", { name: "Close" }).click()

  await page.getByRole("button", { name: "Stop tuning" }).click()
  await expect(page.getByRole("button", { name: "Re-tune" })).toBeVisible()

  await page.getByRole("radio", { name: "Pick configuration membrane_00000" }).click()
  await page.getByText("Customize selected configuration").click()
  await page.getByRole("button", { name: "Run Simulation" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })
})
