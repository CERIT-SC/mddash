import { expect, test } from "@playwright/test"

test("create an experiment from a PDB id", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E creation smoke")
  await page.getByLabel("PDB ID or URL").fill("1LYZ")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  await expect(page.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()
})
