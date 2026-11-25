import { expect, test } from "@playwright/test"

import { stepCard } from "./helpers"

// Seed: enzyme study bbbbb. A running job references the "md" simulation.
test("job-referenced simulation is locked in the setup form", async ({ page }) => {
  await page.goto("experiments/bbbbb")
  // Setup is done once a run exists, so its card starts folded.
  await stepCard(page, "Setup").getByRole("button", { name: "Show Setup" }).click()

  await expect(page.getByText("Locked")).toBeVisible()
  await expect(page.getByLabel("Name", { exact: true })).toBeDisabled()
})
