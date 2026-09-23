import { expect, test } from "@playwright/test"

// Uses the disposable MDPosit-import seed fffff: renamed, then deleted.
test("dashboard chrome: search, rename, and delete an experiment", async ({ page }) => {
  await page.goto("./")

  await page.getByLabel("Search experiments").fill("villin")
  await expect(page.getByRole("link", { name: "AMBER villin headpiece folding" })).toBeVisible()
  await expect(page.getByRole("link", { name: "HIV protease inhibitor binding study" })).toHaveCount(0)

  await page.getByLabel("Search experiments").clear()
  await page.getByRole("button", { name: "Actions for MDPosit imported lysozyme trajectory" }).click()
  await page.getByRole("menuitem", { name: "Rename" }).click()
  await page.getByRole("dialog").getByLabel("Name").fill("E2E renamed import")
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click()
  await expect(page.getByRole("link", { name: "E2E renamed import" })).toBeVisible()

  await page.getByRole("button", { name: "Actions for E2E renamed import" }).click()
  await page.getByRole("menuitem", { name: "Delete" }).click()
  await page.getByRole("button", { name: "Delete experiment" }).click()
  await expect(page.getByRole("link", { name: "E2E renamed import" })).toHaveCount(0)
})
