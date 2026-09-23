import { expect, test } from "@playwright/test"

// Seed: publishable study hhhhh (FINISHED GMX run, unpublished).
test("publish the finished experiment to MDRepo", async ({ page }) => {
  await page.goto("experiments/hhhhh")
  await page.getByRole("button", { name: /Go to section 5: Publish/ }).click()

  await page.getByRole("link", { name: /sign-in/i }).click()
  await page.getByRole("button", { name: "Upload", exact: true }).click()

  // Transitional UI: mutation-driven "Uploading…" button and/or status-doc texts.
  await expect(
    page
      .getByRole("button", { name: "Uploading…" })
      .or(page.getByText(/Upload queued|Uploading files/))
      .first()
  ).toBeVisible()
  // Demo end state: files sit in an MDRepo draft; finalization happens in MDRepo-UI (absent in the demo).
  await expect(page.getByRole("link", { name: "Finish in MDRepo" })).toBeVisible({ timeout: 30_000 })
})
