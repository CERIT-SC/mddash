import { expect, test } from "@playwright/test"

import { stepCard } from "./helpers"

// Seed: lllll and mmmmm hold a setup.ipynb and no simulation. The demo setup Job steps through
// eight fake steps; mmmmm's notebook carries the fail marker, so it stops at step 4.
test("run setup headless: progress, then Configuration", async ({ page }) => {
  await page.goto("experiments/lllll")

  await stepCard(page, "Setup").getByRole("button", { name: "Run setup" }).click()

  await expect(page.getByRole("status")).toContainText(/Starting setup|Step \d of 8/)
  await expect(page.getByRole("tab", { name: "md", exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(stepCard(page, "Configuration")).toHaveAttribute("aria-current", "step")
})

test("a failed setup points to the notebook", async ({ page }) => {
  await page.goto("experiments/mmmmm")

  await stepCard(page, "Setup").getByRole("button", { name: "Run setup" }).click()

  await expect(stepCard(page, "Setup").getByRole("alert")).toContainText("Setup stopped at step 4 of 8 · Add ions", {
    timeout: 30_000,
  })
  await stepCard(page, "Setup").getByRole("button", { name: "Fix in notebook" }).click()
  await expect(page.getByRole("tab", { name: "In notebook" })).toHaveAttribute("aria-selected", "true")
})
