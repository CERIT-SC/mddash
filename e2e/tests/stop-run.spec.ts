import { expect, test } from "@playwright/test"

import { openRunSection } from "./helpers"

// Seed: villin study ddddd, AMBER job demo-amber-running on simulation "villin_equilibration".
test("stop the seeded running AMBER job", async ({ page }) => {
  await openRunSection(page, "ddddd", "villin_equilibration")

  await page.getByRole("button", { name: "Stop run" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Stop run" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Stopped")
  // Extend is GROMACS-only; a stopped AMBER run offers Re-run instead.
  await expect(page.getByRole("button", { name: "Extend", exact: true })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Re-run" })).toBeVisible()
})
