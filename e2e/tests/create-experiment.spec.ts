import { expect, test } from "@playwright/test"

import { stepCard } from "./helpers"

test("create an experiment from a PDB id", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E creation smoke")
  await page.getByLabel("PDB ID or URL").fill("1LYZ")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  await expect(stepCard(page, "Setup")).toHaveAttribute("aria-current", "step")
})

test("opens the provisional experiment immediately and finalizes the import", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E Datahugger journey")
  await page.getByRole("tab", { name: "Datahugger-NG" }).click()
  // "demo-slow" stretches the demo download so the provisional state is observable
  await page.getByLabel("Repository URL").fill("https://github.com/owner/demo-slow-dataset")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  // The 202 closes the dialog and opens the provisional experiment with live progress.
  await expect(page).toHaveURL(/\/experiments\/[a-z0-9]+/)
  await expect(page.getByRole("button", { name: "Cancel import" })).toBeVisible()

  // The progress survives navigation: the dashboard lists the import in its own
  // Populating group, and returning to the experiment resumes the import view.
  await page.getByRole("link", { name: "Home", exact: true }).click()
  await expect(page.getByRole("heading", { name: /Populating/ })).toBeVisible()
  await page.getByRole("link", { name: "E2E Datahugger journey" }).click()
  await expect(page.getByRole("button", { name: "Cancel import" })).toBeVisible()

  // The demo worker and the API monitor finalize within a few seconds; the
  // provisional experiment then transitions to the ordinary wizard.
  await expect(stepCard(page, "Setup")).toBeVisible({ timeout: 30_000 })
})

test("cancels a Datahugger-NG import mid-download", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E Datahugger cancel")
  await page.getByRole("tab", { name: "Datahugger-NG" }).click()
  await page.getByLabel("Repository URL").fill("https://github.com/owner/demo-slow-dataset")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  await expect(page.getByRole("button", { name: "Cancel import" })).toBeVisible()
  await page.getByRole("button", { name: "Cancel import" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "Cancel import" }).click()

  // The cancellation is durable: the experiment stays in the list with the notice.
  await expect(page.getByText("Import cancelled")).toBeVisible()
  await expect(page.getByText(/The repository import was cancelled/)).toBeVisible()

  // And it keeps its place in the Populating group on the dashboard until deletion.
  await page.getByRole("link", { name: "Home", exact: true }).click()
  await expect(page.getByRole("heading", { name: /Populating/ })).toBeVisible()
})

test("shows a durable failure for a failed Datahugger-NG import", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "New", exact: true }).click()
  await page.getByRole("button", { name: "Use custom workflow" }).click()

  await page.getByLabel("Name").fill("E2E Datahugger failure")
  await page.getByRole("tab", { name: "Datahugger-NG" }).click()
  // "demo-fail" in the URL is the demo fake's deterministic download failure
  await page.getByLabel("Repository URL").fill("https://github.com/owner/demo-fail-dataset")
  await page.getByRole("button", { name: "Create Experiment" }).click()

  // The dialog still closes on 202; the failure is durable on the experiment page
  // (safe error plus last measured progress), not a toast.
  await expect(page).toHaveURL(/\/experiments\/[a-z0-9]+/)
  await expect(page.getByText("Import failed")).toBeVisible()
  await expect(page.getByText("The downloaded repository files failed size or checksum validation.")).toBeVisible()
  await expect(page.getByText(/2 of 5 files present/)).toBeVisible()
})
