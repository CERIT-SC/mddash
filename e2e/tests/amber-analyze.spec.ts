import { expect, test } from "@playwright/test"

// Seed: DNA study eeeee, FINISHED RMSD analysis on simulation "dna".
test("view finished AMBER analysis results and the trajectory viewer", async ({ page }) => {
  await page.goto("experiments/eeeee")
  await page.getByRole("button", { name: /Go to section 4: Analyze/ }).click()

  await expect(page.getByRole("button", { name: "Reload Models" })).toBeVisible()

  await page.getByRole("tab", { name: "Analyze" }).click()
  await page.getByRole("combobox", { name: "Analysis" }).click()
  await page.getByRole("option", { name: /RMSD.*ready/ }).click()

  await expect(page.getByRole("button", { name: "Re-calculate" })).toBeVisible()
  await expect(page.getByText("Reference:")).toBeVisible()
})
