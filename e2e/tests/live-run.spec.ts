import { expect, test } from "@playwright/test"

// Seed: enzyme study bbbbb, GMX job demo-gmx-running on simulation "md".
test("open seeded live experiment from the dashboard", async ({ page }) => {
  await page.goto("./")
  await page.getByRole("link", { name: "HIV protease inhibitor binding study" }).click()

  await expect(page.getByRole("tab", { name: "md", exact: true })).toHaveAttribute("aria-selected", "true")
  await page.getByRole("button", { name: /Go to section 3: Run/ }).click()
  await expect(page.getByRole("region", { name: "Run progress" })).toContainText("%")

  await page.getByRole("button", { name: /Logs/ }).click()
  await expect(page.getByText(/GROMACS/).first()).toBeVisible()
})
