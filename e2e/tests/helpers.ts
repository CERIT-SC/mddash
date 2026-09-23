import { expect, type Page } from "@playwright/test"

// The wizard lands on the ladder step (often Analyze for live runs); reach the Run view explicitly.
export async function openRunSection(page: Page, experimentId: string, simulation?: string) {
  await page.goto(`experiments/${experimentId}`)
  if (simulation) {
    await page.getByRole("tab", { name: simulation, exact: true }).click()
  }
  await page.getByRole("button", { name: /Go to section 3: Run/ }).click()
  await expect(page.getByRole("region", { name: "Run progress" })).toBeVisible()
}

export function demoDataFile(name: string): string {
  return new URL(`../../dashboard/api/_demo/data/${name}`, import.meta.url).pathname
}
