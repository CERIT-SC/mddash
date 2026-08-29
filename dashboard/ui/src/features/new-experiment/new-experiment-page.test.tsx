import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { CATALOG_MODULES } from "@/shared/fixtures/notebook-module"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { NewExperimentPage, type NewExperimentSearch } from "./new-experiment-page"

const NOTEBOOKS_REPO = "https://example.test/notebooks.git"

function stubCatalog(override?: () => Response) {
  vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const url = requestUrl(input)
    if (url.includes("notebook-modules")) return override ? override() : Response.json(CATALOG_MODULES)
    return Response.json([])
  })
}

function renderPage(
  search: NewExperimentSearch = {},
  onSearchChange: (next: NewExperimentSearch) => void = () => undefined
) {
  return renderWithProviders(
    <NewExperimentPage search={search} onSearchChange={onSearchChange} defaultNotebooksRepo={NOTEBOOKS_REPO} />
  )
}

describe("NewExperimentPage", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("groups catalog modules under engine sections with GMX first", async () => {
    stubCatalog()
    await renderPage()

    expect(await screen.findByRole("heading", { name: "GROMACS" })).toBeVisible()
    expect(screen.getByRole("heading", { name: "AMBER" })).toBeVisible()
    const gmxCards = screen.getAllByRole("button", { name: /· GROMACS$/ })
    expect(gmxCards.map((card) => card.textContent)).toEqual(["Protein", "Protein (BioBB)", "Membrane protein (BioBB)"])
    expect(screen.getAllByRole("button", { name: /· AMBER$/ })).toHaveLength(2)
    // subtitle = category · engine
    expect(screen.getAllByText("Protein · GROMACS")).toHaveLength(2)
    expect(screen.getByText("Membrane protein · GROMACS")).toBeVisible()
    // truncated texts expose their full content on hover (name span, description z-10)
    expect(screen.getByTitle("Membrane protein (BioBB)")).toHaveClass("truncate")
    expect(screen.getByTitle(/membrane-embedded/)).toHaveClass("line-clamp-2")
    expect(screen.getAllByText("e-INFRA")).toHaveLength(2)
    expect(screen.getAllByText("BioBB")).toHaveLength(3)
  })

  it("shows a loading skeleton while the catalog loads", async () => {
    stubCatalog()
    await renderPage()
    expect(screen.getByLabelText("Loading workflows")).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: "GROMACS" })).toBeVisible()
  })

  it("reports catalog failures with a retry and keeps the custom workflow available", async () => {
    let calls = 0
    stubCatalog(() => {
      calls += 1
      return calls === 1
        ? Response.json(
            { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
            { status: 503 }
          )
        : Response.json(CATALOG_MODULES)
    })
    const user = userEvent.setup()
    await renderPage()

    expect(await screen.findByRole("alert")).toHaveTextContent("urn:mddash:upstream-unavailable")
    await user.click(screen.getByRole("button", { name: /use custom workflow/i }))
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByLabelText(/notebooks repository/i)).toHaveValue(NOTEBOOKS_REPO)
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Retry" }))
    expect(await screen.findByRole("heading", { name: "GROMACS" })).toBeVisible()
  })

  it("filters sections through the engine tabs", async () => {
    stubCatalog()
    const onSearchChange = vi.fn()
    const user = userEvent.setup()
    const view = await renderPage({}, onSearchChange)
    await screen.findByRole("heading", { name: "GROMACS" })

    await user.click(screen.getByRole("tab", { name: "AMBER" }))
    expect(onSearchChange).toHaveBeenCalledWith({ engine: "amber" })
    view.unmount()

    // with the filter applied from the URL, "All" clears it
    const onClear = vi.fn()
    await renderPage({ engine: "amber" }, onClear)
    await user.click(screen.getByRole("tab", { name: "All" }))
    expect(onClear).toHaveBeenCalledWith({})
  })

  it("shows only the requested engine when the filter is active", async () => {
    stubCatalog()
    await renderPage({ engine: "amber" })

    expect(await screen.findByRole("heading", { name: "AMBER" })).toBeVisible()
    expect(screen.queryByRole("heading", { name: "GROMACS" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /· AMBER$/ })).toHaveLength(2)
  })

  it("shows an engine-scoped empty state when the filter matches no modules", async () => {
    stubCatalog(() => Response.json(CATALOG_MODULES.filter((module) => module.engine === "GMX")))
    await renderPage({ engine: "amber" })

    expect(await screen.findByText("No AMBER workflows available.")).toBeVisible()
    expect(screen.queryByRole("button", { name: /· AMBER$/ })).not.toBeInTheDocument()
  })

  it("shows an empty state when the catalog has no modules at all", async () => {
    stubCatalog(() => Response.json([]))
    await renderPage()

    expect(await screen.findByText("No workflows available.")).toBeVisible()
  })

  it("opens the creation dialog for a card and returns to the gallery on cancel", async () => {
    stubCatalog()
    const user = userEvent.setup()
    await renderPage()

    await user.click(await screen.findByRole("button", { name: "Protein (BioBB) · AMBER" }))
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByRole("heading", { name: "New Experiment: Protein (BioBB)" })).toBeVisible()
    expect(within(dialog).getByText("Protein · AMBER")).toBeVisible()
    // the preset fixes the engine — no engine choice to make
    expect(within(dialog).queryByRole("radio", { name: "GROMACS" })).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Protein (BioBB) · AMBER" })).toBeVisible()
  })

  it("links back to the dashboard", async () => {
    stubCatalog()
    await renderPage()
    expect(screen.getByRole("link", { name: "Back to My Experiments" })).toBeVisible()
  })
})
