import { expect, test } from "@playwright/test"

// Seed: tetrapeptide study iiiii, valid AMBER simulation, no jobs.
// Manual configuration submits an AMBER job that finishes via the staged E2E schedule.
test("manual configuration: submit an AMBER production run", async ({ page }) => {
  await page.goto("experiments/iiiii")
  await page.getByRole("button", { name: /Go to section 2: Tune/ }).click()

  await page.getByRole("tab", { name: "Manual configuration" }).click()
  await page.getByRole("combobox", { name: "Binary" }).click()
  await page.getByRole("option", { name: "pmemd.cuda (GPU)" }).click()
  await page.getByRole("combobox", { name: "Ewald preset" }).click()
  await page.getByRole("option", { name: "Optimized" }).click()
  await page.getByLabel("MPI Processes (MPI ranks)").fill("1")
  await page.getByLabel("Threads").fill("2")

  await page.getByRole("button", { name: "Run Simulation" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })
})
