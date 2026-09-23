import { expect, test } from "@playwright/test"

// Two notebooks are seeded RUNNING (enzyme + villin) and the demo limit is 2, so any
// further start hits the limit dialog. Sequential journey: limit → stop villin's →
// start DNA's → stop it again. Runs on the dashboard card menus.
test("notebook lifecycle: limit dialog, stop, and start", async ({ page }) => {
  await page.goto("./")

  await page.getByRole("button", { name: "Actions for AMBER DNA duplex stability" }).click()
  await page.getByRole("menuitem", { name: "Start notebook" }).click()
  await expect(page.getByRole("dialog").getByText("Notebook limit reached")).toBeVisible()
  await expect(page.getByRole("dialog").getByText("HIV protease inhibitor binding study")).toBeVisible()
  await expect(page.getByRole("dialog").getByText("AMBER villin headpiece folding")).toBeVisible()
  await page.getByRole("button", { name: "Cancel", exact: true }).click()

  await page.getByRole("button", { name: "Actions for AMBER villin headpiece folding" }).click()
  await page.getByRole("menuitem", { name: "Stop notebook" }).click()

  await page.getByRole("button", { name: "Actions for AMBER DNA duplex stability" }).click()
  await page.getByRole("menuitem", { name: "Start notebook" }).click()

  // The notebook status bar lives on experiment pages.
  await page.getByRole("link", { name: "AMBER DNA duplex stability" }).click()
  await expect(page.getByRole("region", { name: "Notebook status" })).toBeVisible()
  await expect(
    page.getByRole("region", { name: "Notebook status" }).getByRole("link", { name: "Open notebook" })
  ).toBeVisible()

  await page.getByRole("region", { name: "Notebook status" }).getByRole("button", { name: "Stop notebook" }).click()
  await expect(page.getByRole("region", { name: "Notebook status" })).toBeHidden()
})
