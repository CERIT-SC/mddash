import { expect, test } from "@playwright/test"

// Pockets has no cache payload: the miss ends the job ERROR without network.
// Seed: villin study, simulation "villin".
test("pockets analysis ends in a durable error state", async ({ page }) => {
  await page.goto("experiments/ddddd")

  await page.getByRole("tab", { name: "Analyze" }).click()
  await page.getByRole("combobox", { name: "Analysis" }).click()
  await page.getByRole("option", { name: "Pockets" }).click()
  await page.getByRole("button", { name: "Calculate" }).click()

  await expect(page.getByRole("alert").filter({ hasText: "Previous analysis run failed." })).toBeVisible({
    timeout: 30_000,
  })
})
