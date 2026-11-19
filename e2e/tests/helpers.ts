import { expect, type Page } from "@playwright/test"

// Step cards render together; an unlocked Simulation card shows the run's progress.
export async function openRunSection(page: Page, experimentId: string, simulation?: string) {
  await page.goto(`experiments/${experimentId}`)
  if (simulation) {
    await page.getByRole("tab", { name: simulation, exact: true }).click()
  }
  await expect(page.getByRole("region", { name: "Run progress" })).toBeVisible()
}

// Step content nests lists of its own; only a card's item holds its title heading.
export function stepCard(page: Page, title: string) {
  return page
    .getByRole("list", { name: "Steps" })
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) })
}

export function demoDataFile(name: string): string {
  return new URL(`../../dashboard/api/_demo/data/${name}`, import.meta.url).pathname
}
