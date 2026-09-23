import { expect, test } from "@playwright/test"

import { demoDataFile } from "./helpers"

test("manual setup: upload files and create a GROMACS simulation", async ({ page }) => {
  await page.goto("new")
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E GMX manual setup")
  await page.getByRole("tab", { name: "Upload Files" }).click()
  await page.locator('input[type="file"]').setInputFiles([demoDataFile("md.tpr"), demoDataFile("structure.pdb")])
  await page.getByRole("button", { name: "Create Experiment" }).click()
  await expect(page.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()

  await page.getByRole("tab", { name: "Manual" }).click()
  await page.getByRole("combobox", { name: "Run input (.tpr)" }).click()
  await page.getByRole("option", { name: /md\.tpr/ }).click()
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("md")

  await page.getByRole("combobox", { name: "Reference structure" }).click()
  await page.getByRole("option", { name: /structure\.pdb/ }).click()
  await page.getByRole("button", { name: "Create simulation" }).click()

  await expect(page.getByRole("tab", { name: "md", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Go to Tune" })).toBeEnabled()
})
