import { expect, test } from "@playwright/test"

import { openRunSection } from "./helpers"

// Seed: enzyme study bbbbb, stopped run on simulation "npt_equilibration" that accepts checkpoint extension.
// E2E mode advances the submitted job one stage per status poll. It takes about 3 polls to reach FINISHED.
test("extend the stopped GMX run, then re-run from scratch", async ({ page }) => {
  await openRunSection(page, "bbbbb", "npt_equilibration")
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Stopped")

  await page.getByRole("button", { name: "Extend", exact: true }).click()
  await page.getByLabel("Additional steps").fill("50000")
  await page.getByRole("alertdialog").getByRole("button", { name: "Extend" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })

  // Re-run is a destructive reset. It deletes the run and starts one fresh run.
  await page.getByRole("button", { name: "Re-run" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Re-run" }).click()
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  // One run per simulation, so there is no run-history table.
  await expect(page.getByRole("region", { name: "Run history" })).toHaveCount(0)
})
