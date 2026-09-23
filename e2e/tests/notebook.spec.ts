import { expect, test } from "@playwright/test"

// Two RUNNING notebooks at a demo limit of 2 — every further start routes through the limit dialog.
test("notebook lifecycle: limit dialog, stop, and start", async ({ page }) => {
  await page.goto("./")

  await page.getByRole("button", { name: "Actions for AMBER DNA duplex stability" }).click()
  await page.getByRole("menuitem", { name: "Start notebook" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByText("Notebook limit reached")).toBeVisible()
  await expect(dialog.getByText("HIV protease inhibitor binding study")).toBeVisible()
  await expect(dialog.getByText("AMBER villin headpiece folding")).toBeVisible()

  await dialog.getByRole("button", { name: "Stop notebook for AMBER villin headpiece folding" }).click()
  await dialog.getByRole("button", { name: "Start new notebook" }).click()
  await page.keyboard.press("Escape")

  // The notebook status bar lives on experiment pages.
  await page.getByRole("link", { name: "AMBER DNA duplex stability" }).click()
  await expect(page.getByRole("region", { name: "Notebook status" })).toBeVisible()
  await expect(
    page.getByRole("region", { name: "Notebook status" }).getByRole("link", { name: "Open notebook" })
  ).toBeVisible()

  await page.getByRole("region", { name: "Notebook status" }).getByRole("button", { name: "Stop notebook" }).click()
  await expect(page.getByRole("region", { name: "Notebook status" })).toBeHidden()
})
