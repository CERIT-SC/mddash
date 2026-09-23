import { expect, test } from "@playwright/test"

// Seed: lysozyme study ccccc is published to MDRepo (mdrepo_published).
test("view an already-published experiment", async ({ page }) => {
  await page.goto("experiments/ccccc")
  await page.getByRole("button", { name: /Go to section 5: Publish/ }).click()

  await expect(page.getByRole("alert").filter({ hasText: "Published" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Copy record link" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Publish a new version" })).toBeDisabled()
})
