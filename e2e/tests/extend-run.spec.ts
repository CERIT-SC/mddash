import { expect, test } from "@playwright/test"

import { openRunSection } from "./helpers"

// Seed: enzyme study bbbbb, stopped (checkpoint-extendable) run on simulation "npt_equilibration".
// E2E mode advances the submitted job one stage per status poll: ~3 polls to FINISHED.
test("extend the stopped GMX run, then re-run from scratch", async ({ page }) => {
  await openRunSection(page, "bbbbb", "npt_equilibration")
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Stopped")

  await page.getByRole("button", { name: "Extend", exact: true }).click()
  await page.getByLabel("Additional steps").fill("50000")
  await page.getByRole("alertdialog").getByRole("button", { name: "Extend" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })

  // Re-run is the destructive reset: the run is deleted and one fresh run starts.
  await page.getByRole("button", { name: "Re-run" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Re-run" }).click()
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  // One run per simulation: no run-history table.
  await expect(page.getByRole("region", { name: "Run history" })).toHaveCount(0)
})
