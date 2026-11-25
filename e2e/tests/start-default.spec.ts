import { expect, test } from "@playwright/test"

// Seed: tetrapeptide study iiiii, simulation tetrapeptide_default with setup-suggested resources, no jobs.
test("configuration: start the run with the setup's default resources", async ({ page }) => {
  await page.goto("experiments/iiiii?simulation=tetrapeptide_default")

  await page.getByRole("button", { name: "Start with default" }).click()

  await expect(page.getByRole("region", { name: "Run progress" })).toContainText(/Preparing|\d+%/)
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("Finished", { timeout: 60_000 })
})
