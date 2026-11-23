import { expect, test } from "@playwright/test"

// Seed: tetrapeptide study iiiii, valid AMBER simulation, no jobs. Pinned to its tab: start-default runs beside it.
// The Expert dialog submits an AMBER job that finishes through the staged E2E schedule.
test("expert configuration: submit an AMBER production run", async ({ page }) => {
  await page.goto("experiments/iiiii?simulation=tetrapeptide")

  await page.getByRole("button", { name: "Expert…" }).click()
  await page.getByRole("combobox", { name: "Binary" }).click()
  await page.getByRole("option", { name: "pmemd.cuda (GPU)" }).click()
  await page.getByRole("combobox", { name: "Ewald preset" }).click()
  await page.getByRole("option", { name: "Optimized" }).click()
  await page.getByLabel("MPI Processes (MPI ranks)").fill("1")
  await page.getByLabel("Threads").fill("2")

  await page.getByRole("dialog").getByRole("button", { name: "Run Simulation" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })
})
