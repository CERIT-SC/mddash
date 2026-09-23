import { expect, test } from "@playwright/test"

// Seed: enzyme study bbbbb, simulation "md" (live run; analyses allowed mid-run).
// E2E mode completes the submitted analysis in 0.5s; the UI notices on its 5s poll.
test("submit an RMSD analysis to completion", async ({ page }) => {
  await page.goto("experiments/bbbbb")
  await page.getByRole("button", { name: /Go to section 4: Analyze/ }).click()
  await page.getByRole("tab", { name: "Analyze" }).click()

  await page.getByRole("combobox", { name: "Analysis" }).click()
  await page.getByRole("option", { name: "RMSD", exact: true }).click()
  await page.getByRole("button", { name: "Calculate" }).click()

  // Completion (0.5s) races the first poll; assert the terminal state.
  await expect(page.getByRole("button", { name: "Re-calculate" })).toBeVisible({ timeout: 30_000 })
})
