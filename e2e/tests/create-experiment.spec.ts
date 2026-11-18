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

test("create an experiment from a Datahugger-NG repository", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E Datahugger")
  await page.getByRole("tab", { name: "Datahugger-NG" }).click()
  await page.getByLabel("Repository URL").fill("https://github.com/owner/dataset")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  // the 202 switches the dialog to following the background download
  await expect(page.getByText(/downloading the repository/i)).toBeVisible()

  // the demo worker and the API monitor finalize within a few seconds; the
  // dialog then opens the now-existing experiment
  await expect(page.getByRole("heading", { name: "Set up your simulation" })).toBeVisible()
})

test("shows a durable error when Datahugger-NG population fails", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E Datahugger failure")
  await page.getByRole("tab", { name: "Datahugger-NG" }).click()
  // "demo-fail" in the URL is the demo fake's deterministic download failure
  await page.getByLabel("Repository URL").fill("https://github.com/owner/demo-fail-dataset")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  // the terminal failure stays in the dialog, not a toast
  await expect(page.getByText("Experiment creation failed")).toBeVisible()
  await expect(page.getByText("The repository download failed.")).toBeVisible()
  await expect(page.getByRole("button", { name: "Create Experiment" })).toBeDisabled()
})
