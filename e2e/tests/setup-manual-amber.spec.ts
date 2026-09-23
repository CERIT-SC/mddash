import { expect, test } from "@playwright/test"

import { demoDataFile } from "./helpers"

test("manual setup: upload files and create an AMBER simulation", async ({ page }) => {
  await page.goto("new")
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E AMBER manual setup")
  await page.getByRole("tab", { name: "AMBER" }).click()
  await page.getByRole("tab", { name: "Upload Files" }).click()
  await page
    .locator('input[type="file"]')
    .setInputFiles([
      demoDataFile("md.parm7"),
      demoDataFile("md.inpcrd"),
      demoDataFile("md.mdin"),
      demoDataFile("amber_structure.pdb"),
    ])
  await page.getByRole("button", { name: "Create Experiment" }).click()
  await expect(page.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()

  await page.getByRole("tab", { name: "Manual" }).click()
  await page.getByRole("combobox", { name: "Run control" }).click()
  await page.getByRole("option", { name: /md\.mdin/ }).click()
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("md")

  await page.getByRole("combobox", { name: "Topology" }).click()
  await page.getByRole("option", { name: /md\.parm7/ }).click()
  await page.getByRole("combobox", { name: "Coordinates" }).click()
  await page.getByRole("option", { name: /md\.inpcrd/ }).click()
  await page.getByRole("combobox", { name: "Reference structure" }).click()
  await page.getByRole("option", { name: /amber_structure\.pdb/ }).click()
  await page.getByRole("button", { name: "Create simulation" }).click()

  await expect(page.getByRole("tab", { name: "md", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Go to Tune" })).toBeEnabled()
})
