import { expect, test } from "@playwright/test"

import { openRunSection } from "./helpers"

// Seed: enzyme study bbbbb, STOPPED second segment on simulation "npt_equilibration".
// E2E mode advances the submitted job one stage per status poll: ~3 polls to FINISHED.
test("extend the stopped GMX segment", async ({ page }) => {
  await openRunSection(page, "bbbbb", "npt_equilibration")
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Stopped")

  await page.getByRole("button", { name: "Extend", exact: true }).click()
  await page.getByLabel("Additional steps").fill("50000")
  await page.getByRole("alertdialog").getByRole("button", { name: "Extend" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })
})
