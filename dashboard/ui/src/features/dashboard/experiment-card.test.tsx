import type { Experiment } from "@/api/generated/models"
import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockFetch, requestUrl } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ExperimentCard } from "./experiment-card"

// Suite baseline: the card under test is always experiment exp1 named "Analyze".
const analyze = (overrides: Partial<Experiment> = {}) => experiment("exp1", { name: "Analyze", ...overrides })

function renderCard(exp: Experiment) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ExperimentCard experiment={exp} />
    </QueryClientProvider>
  )
}

describe("ExperimentCard", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("renders name, engine, step progress and idle status line", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(analyze())
    expect(screen.getByText("Analyze")).toBeVisible()
    expect(screen.getByText("Custom · GROMACS")).toBeVisible()
    expect(screen.getByText("Tune · 2 of 5")).toBeVisible()
    expect(screen.getByRole("progressbar", { name: "Workflow progress: step 2 of 5" })).toBeInTheDocument()
    expect(screen.getByText("Active 12 min ago")).toBeVisible()
  })

  it("shows the live phase for active statuses", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(analyze({ step: 3, status: "simulating" }))
    expect(screen.getByText("Run · 3 of 5")).toBeVisible()
    expect(screen.getByText("Simulating")).toBeVisible()
  })

  it("offers Stop notebook when the notebook is up, Start notebook when down", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const user = userEvent.setup()

    const { unmount } = renderCard(analyze({ notebook: withNotebook("RUNNING") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    expect(screen.getByRole("menuitem", { name: /stop notebook/i })).toBeVisible()
    unmount()

    renderCard(analyze({ notebook: withNotebook("DOWN") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    expect(screen.getByRole("menuitem", { name: /start notebook/i })).toBeVisible()
    expect(screen.getByRole("menuitem", { name: /duplicate/i })).toHaveAttribute("aria-disabled", "true")
    expect(screen.getByRole("menuitem", { name: /^archive$/i })).toHaveAttribute("aria-disabled", "true")
  })

  it("renames via dialog", async () => {
    const calls = mockFetch(new Response("{}", { status: 200 }), new Response("[]", { status: 200 }))
    const user = userEvent.setup()
    renderCard(analyze())
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /rename/i }))
    const input = screen.getByLabelText("Name")
    await user.clear(input)
    await user.type(input, "Renamed")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1"),
      method: "PATCH",
      body: { name: "Renamed" },
    })
    // closes and invalidates the list
    await screen.findByText("Analyze")
  })

  it("deletes after confirmation", async () => {
    const calls = mockFetch(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    renderCard(analyze())
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /^delete$/i }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1"),
      method: "DELETE",
      body: undefined,
    })
  })

  it("shows the module name, source label, and size when present", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(
      analyze({ module_name: "Membrane protein (BioBB)", source_label: "PDB (1BNA)", size_bytes: 8.7 * 1024 ** 3 })
    )
    expect(screen.getByText("Membrane protein (BioBB) · GROMACS")).toBeVisible()
    expect(screen.getByText("PDB (1BNA)")).toBeVisible()
    expect(screen.getByText("8.7 GB")).toBeVisible()
  })

  it("shows setup details on a setup-step card", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(analyze({ step: 1, status: "setup complete" }))
    expect(screen.getByText("Setup ready")).toBeVisible()
    expect(screen.getByText("Yes")).toBeVisible()
    expect(screen.getByText("Workflow")).toBeVisible()
    expect(screen.getByText("Custom")).toBeVisible()
  })

  it("shows tuner details on a tune-step card", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(
      analyze({
        step: 2,
        status: "tuning",
        latest_simulation_path: "md.simulation.json",
        tuner_jobs: [
          {
            id: "t1",
            experiment_id: "exp1",
            simulation_path: "md.simulation.json",
            nsteps: 10000,
            created_at: "2026-08-13T00:00:00Z",
            is_stopped: false,
            engine: "GMX",
            tuner_status: "RUNNING",
            sim_length_ns: 250,
            trials: [
              { id: "a", status: "FINISHED", performance: 70 },
              { id: "b", status: "RUNNING", performance: null },
              { id: "c", performance: null },
            ],
          },
        ],
      })
    )
    expect(screen.getByText("Configurations")).toBeVisible()
    expect(screen.getByText("1 of 3 explored")).toBeVisible()
    expect(screen.getByText("Steps")).toBeVisible()
    expect(screen.getByText("10,000")).toBeVisible()
  })

  it("shows analysis details on an analyze-step card", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = requestUrl(input)
      if (url.includes("/analysis/results")) {
        return Response.json(["rmsd", "clusters"])
      }
      if (url.includes("/analysis/types")) {
        return Response.json(["rmsds", "clusters", "sas", "hbonds"])
      }
      if (url.includes("/analysis")) {
        return Response.json([
          { id: "a1", status: "FINISHED" },
          { id: "a2", status: "RUNNING" },
        ])
      }
      return new Response(null, { status: 404 })
    })
    renderCard(
      analyze({
        step: 4,
        status: "analyzing",
        latest_simulation_path: "md.simulation.json",
        simulation_jobs: [
          {
            id: "s1",
            experiment_id: "exp1",
            simulation_path: "md.simulation.json",
            created_at: "2026-08-13T00:00:00Z",
            engine: "GMX",
            np: 4,
            ntomp: 2,
            status: "FINISHED",
          },
        ],
      })
    )
    expect(await screen.findByText("Models")).toBeVisible()
    expect((await screen.findByText("2")).textContent).toBe("2")
    expect(await screen.findByText("1 of 4 ready")).toBeVisible()
  })

  it("falls back to N/A when step detail data is missing", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(analyze({ step: 2, status: "tuning", latest_simulation_path: "md.simulation.json" }))
    expect(screen.getAllByText("N/A")).toHaveLength(2)
  })

  it("shows different icons for the publishing and published states", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const { container, unmount } = renderCard(analyze({ step: 5, status: "publishing", mdrepo_published: false }))
    expect(container.querySelector("span.bg-info-100")).not.toBeNull()
    expect(container.querySelector("span.bg-primary-100")).toBeNull()
    unmount()
    const published = renderCard(analyze({ step: 5, status: "published", mdrepo_published: true }))
    expect(published.container.querySelector("span.bg-primary-100")).not.toBeNull()
  })

  it("shows publish details on a publish-step card", () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    renderCard(analyze({ step: 5, status: "published", mdrepo_published: true, mdrepo_id: "10.5281/demo" }))
    expect(screen.getByText("Published")).toBeVisible()
    expect(screen.getByText("Yes")).toBeVisible()
    expect(screen.getByText("Target")).toBeVisible()
    expect(screen.getByText("Invenio / MDRepo")).toBeVisible()
    expect(screen.getByText("10.5281/demo")).toBeVisible()
  })

  it("closes the rename dialog from Cancel without a request", async () => {
    const calls: { url: string; method: string }[] = []
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: requestUrl(input), method: init?.method ?? "GET" })
      return new Response("[]", { status: 200 })
    })
    const user = userEvent.setup()
    renderCard(analyze())
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /rename/i }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(calls.find((call) => call.method !== "GET")).toBeUndefined()
  })

  it("starts a down notebook from the menu", async () => {
    const calls = mockFetch(new Response("{}", { status: 200 }), new Response("[]", { status: 200 }))
    const user = userEvent.setup()
    renderCard(analyze({ notebook: withNotebook("DOWN") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /start notebook/i }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1/notebook"),
      method: "POST",
      body: {},
    })
  })
})
