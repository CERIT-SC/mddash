import { expect, test } from "@playwright/test"

// Seed: jjjjj KIX study — FINISHED GMX run with trajectory, nothing live, unpublished.
test("prepare an MDPosit handoff package", async ({ page }) => {
  await page.goto("experiments/jjjjj")
  await page.getByRole("button", { name: /Go to section 5: Publish/ }).click()

  await page.getByRole("combobox", { name: "Publication target" }).click()
  await page.getByRole("option", { name: "MDPosit" }).click()
  await page.getByRole("button", { name: "Prepare MDPosit handoff" }).click()

  await expect(page.getByRole("link", { name: "Metadata file (inputs.yaml)" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole("link", { name: "Structure file" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Topology file" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Trajectory file" })).toBeVisible()
})
