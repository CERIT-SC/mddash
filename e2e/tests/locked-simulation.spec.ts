import { expect, test } from "@playwright/test"

// Seed: enzyme study bbbbb; the "md" simulation is referenced by a running job.
test("job-referenced simulation is locked in the setup form", async ({ page }) => {
  await page.goto("experiments/bbbbb")
  await page.getByRole("button", { name: /Go to section 1: Setup/ }).click()

  await expect(page.getByText("Locked")).toBeVisible()
  await expect(page.getByLabel("Name", { exact: true })).toBeDisabled()
})
