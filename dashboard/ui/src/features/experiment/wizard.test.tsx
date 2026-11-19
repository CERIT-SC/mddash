import { Step, type Experiment, type Simulation } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { simulation } from "@/shared/fixtures/simulation"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ExperimentWizard, type WizardSearch } from "./wizard"

const SIM = "md.simulation.json"

type Options = { sims?: Simulation[]; exp?: Partial<Experiment>; search?: WizardSearch }

async function renderWizard({ sims, exp, search = {} }: Options = {}) {
  mockApiBySuffix({
    "/experiments/exp1/simulations": Response.json(sims ?? [simulation(SIM, { name: "protein", valid: true })]),
    "/experiments/exp1": Response.json(experiment("exp1", { latest_simulation_path: SIM, can_publish: false, ...exp })),
  })
  const onSearchChange = vi.fn()
  const view = await renderWithProviders(
    <ExperimentWizard experimentId="exp1" search={search} onSearchChange={onSearchChange} />
  )
  return Object.assign(view, { onSearchChange })
}

async function stepCards() {
  const list = await screen.findByRole("list", { name: "Steps" })
  // Step content nests lists of its own (the setup guide); only direct items are cards.
  return within(list)
    .getAllByRole("listitem")
    .filter((item) => item.parentElement === list)
}

function card(cards: HTMLElement[], title: string): HTMLElement {
  const found = cards.find((item) => within(item).queryByRole("heading", { name: title }) !== null)
  if (found === undefined) throw new Error(`No step card titled ${title}`)
  return found
}

afterEach(() => vi.unstubAllGlobals())

describe("ExperimentWizard step cards", () => {
  it("lists the four steps in the order the API declares them", async () => {
    await renderWizard()
    // The card title is each item's first heading; step content may add its own below.
    const titles = (await stepCards()).map((item) => within(item).getAllByRole("heading")[0]?.textContent)
    expect(titles).toEqual(["Setup", "Configuration", "Simulation", "Analysis"])
  })

  it("marks the reached step current, folds finished ones, and explains locked ones", async () => {
    await renderWizard({ sims: [simulation(SIM, { name: "protein", valid: true, step: Step.configuration })] })
    const cards = await stepCards()

    expect(card(cards, "Configuration")).toHaveAttribute("aria-current", "step")
    expect(within(card(cards, "Setup")).getByText("“protein” is ready")).toBeInTheDocument()
    expect(within(card(cards, "Setup")).getByRole("button", { name: "Show Setup" })).toBeInTheDocument()
    expect(within(card(cards, "Simulation")).getByText("Starts after you choose a configuration")).toBeInTheDocument()
    expect(
      within(card(cards, "Analysis")).getByText("Available once the run saves its first frames")
    ).toBeInTheDocument()
    expect(cards.filter((item) => item.hasAttribute("aria-current"))).toHaveLength(1)
  })

  it("keeps a live run current while its saved frames already open Analysis", async () => {
    await renderWizard({
      sims: [simulation(SIM, { name: "protein", valid: true, step: Step.analysis, status: "simulating", live: true })],
    })
    const cards = await stepCards()

    expect(card(cards, "Simulation")).toHaveAttribute("aria-current", "step")
    expect(card(cards, "Analysis")).not.toHaveAttribute("aria-current")
    expect(within(card(cards, "Analysis")).queryByText(/Available once/)).not.toBeInTheDocument()
  })

  it("opens only Setup on the create tab", async () => {
    await renderWizard({ sims: [] })
    const cards = await stepCards()

    expect(card(cards, "Setup")).toHaveAttribute("aria-current", "step")
    expect(within(card(cards, "Configuration")).getByText("Available once the setup finishes")).toBeInTheDocument()
  })
})

describe("ExperimentWizard publish", () => {
  it("keeps Publish disabled with the reason until something is publishable", async () => {
    await renderWizard()
    expect(await screen.findByRole("button", { name: "Publish…" })).toBeDisabled()
    expect(screen.getByText("Publish unlocks once a run has finished or been stopped.")).toBeInTheDocument()
  })

  it("opens the Publish dialog through the URL", async () => {
    const user = userEvent.setup()
    const view = await renderWizard({
      sims: [simulation(SIM, { name: "protein", valid: true, step: Step.analysis, status: "analyzing" })],
      exp: { can_publish: true },
    })
    await user.click(await screen.findByRole("button", { name: "Publish…" }))
    expect(view.onSearchChange).toHaveBeenCalledWith(expect.objectContaining({ publish: true }))
  })

  it("shows the Publish dialog while the URL asks for it", async () => {
    await renderWizard({
      sims: [simulation(SIM, { name: "protein", valid: true, step: Step.analysis, status: "analyzing" })],
      exp: { can_publish: true },
      search: { publish: true },
    })
    expect(await screen.findByRole("dialog", { name: "Publish your experiment" })).toBeInTheDocument()
  })
})
