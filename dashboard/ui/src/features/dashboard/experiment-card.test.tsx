import type { Experiment } from "@/api/generated/models"
import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockFetch, requestUrl } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ExperimentCard } from "./experiment-card"

// Suite baseline: the card under test is always experiment exp1 named "Analyze".
const analyze = (overrides: Partial<Experiment> = {}) => experiment("exp1", { name: "Analyze", ...overrides })

function renderCard(exp: Experiment) {
  return renderWithProviders(<ExperimentCard experiment={exp} />)
}

describe("ExperimentCard", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("renders name, engine, step progress and idle status line", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(analyze())
    expect(screen.getByText("Analyze")).toBeVisible()
    expect(screen.getByText("Custom · GROMACS")).toBeVisible()
    expect(screen.getByText("Tune · 2 of 5")).toBeVisible()
    expect(screen.getByRole("progressbar", { name: "Workflow progress: step 2 of 5" })).toBeInTheDocument()
    expect(screen.getByText("Active 12 min ago")).toBeVisible()
  })

  it("shows the live phase for active statuses", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(analyze({ step: 3, status: "simulating" }))
    expect(screen.getByText("Run · 3 of 5")).toBeVisible()
    expect(screen.getByText("Simulating")).toBeVisible()
  })

  it("offers Stop notebook when the notebook is up, Start notebook when down", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const user = userEvent.setup()

    const { unmount } = await renderCard(analyze({ notebook: withNotebook("RUNNING") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    expect(screen.getByRole("menuitem", { name: /stop notebook/i })).toBeVisible()
    unmount()

    await renderCard(analyze({ notebook: withNotebook("DOWN") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    expect(screen.getByRole("menuitem", { name: /start notebook/i })).toBeVisible()
    expect(screen.getByRole("menuitem", { name: /duplicate/i })).toHaveAttribute("aria-disabled", "true")
    expect(screen.getByRole("menuitem", { name: /^archive$/i })).toHaveAttribute("aria-disabled", "true")
  })

  it("renames via dialog", async () => {
    const calls = mockFetch(new Response("{}", { status: 200 }), new Response("[]", { status: 200 }))
    const user = userEvent.setup()
    await renderCard(analyze())
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
    await renderCard(analyze())
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /^delete$/i }))
    await user.click(screen.getByRole("button", { name: "Delete experiment" }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1"),
      method: "DELETE",
      body: undefined,
    })
  })

  it("spells out delete consequences from experiment data", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const user = userEvent.setup()
    await renderCard(
      analyze({
        size_bytes: 12.8 * 1024 ** 3,
        notebook: withNotebook("RUNNING"),
        simulation_jobs: [
          {
            id: "s1",
            experiment_id: "exp1",
            simulation_path: "md.simulation.json",
            created_at: "2026-08-13T00:00:00Z",
            engine: "GMX",
            np: 4,
            ntomp: 2,
            status: "RUNNING",
          },
          {
            id: "s2",
            experiment_id: "exp1",
            simulation_path: "md.simulation.json",
            created_at: "2026-08-13T00:00:00Z",
            engine: "GMX",
            np: 4,
            ntomp: 2,
            status: "FINISHED",
          },
        ],
        tuner_jobs: [
          {
            id: "t1",
            experiment_id: "exp1",
            simulation_path: "md.simulation.json",
            nsteps: 10000,
            created_at: "2026-08-13T00:00:00Z",
            is_stopped: false,
            engine: "GMX",
            tuner_status: "PENDING",
            trials: [],
          },
        ],
      })
    )
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /^delete$/i }))
    expect(screen.getByText("Delete experiment “Analyze”?")).toBeVisible()
    expect(screen.getByText(/all simulation files and results \(12.8 GB\)/i)).toBeVisible()
    expect(screen.getByText(/the experiment’s notebook/i)).toBeVisible()
    expect(screen.getByText(/2 running or queued jobs/i)).toBeVisible()
    expect(screen.getByText(/this can’t be undone/i)).toBeVisible()
    // Archive is offered as a reversible alternative but not implemented in the API yet
    expect(screen.getByText(/want to keep the results/i)).toBeVisible()
    expect(screen.getByRole("button", { name: /archive instead/i })).toBeDisabled()
  })

  it("omits absent consequences from the delete dialog", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const user = userEvent.setup()
    await renderCard(analyze())
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /^delete$/i }))
    expect(screen.getByText(/^all simulation files and results$/i)).toBeVisible()
    expect(screen.queryByText(/the experiment’s notebook/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/running or queued/i)).not.toBeInTheDocument()
    expect(screen.getByText(/archiving frees disk space/i)).toBeVisible()
  })

  it("shows the module name, source label, and size when present", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(
      analyze({
        module_name: "Membrane protein (BioBB)",
        source: { type: "pdb", pdb_id: "1BNA", files: [] },
        size_bytes: 8.7 * 1024 ** 3,
      })
    )
    expect(screen.getByText("Membrane protein (BioBB) · GROMACS")).toBeVisible()
    expect(screen.getByText("RCSB PDB (1BNA)")).toBeVisible()
    expect(screen.getByText("8.7 GB")).toBeVisible()
  })

  it("shows setup details on a setup-step card", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(analyze({ step: 1, status: "setup complete" }))
    expect(screen.getByText("Setup ready")).toBeVisible()
    expect(screen.getByText("Yes")).toBeVisible()
    expect(screen.getByText("Workflow")).toBeVisible()
    expect(screen.getByText("Custom")).toBeVisible()
  })

  it("shows tuner details on a tune-step card", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(
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
    await renderCard(
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

  it("falls back to N/A when step detail data is missing", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(analyze({ step: 2, status: "tuning", latest_simulation_path: "md.simulation.json" }))
    expect(screen.getAllByText("N/A")).toHaveLength(2)
  })

  it("shows different icons for the publishing and published states", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    const { container, unmount } = await renderCard(analyze({ step: 5, status: "publishing", mdrepo_published: false }))
    expect(container.querySelector("span.bg-info.text-info-foreground")).not.toBeNull()
    expect(container.querySelector("span.bg-primary.text-primary-foreground")).toBeNull()
    unmount()
    const published = await renderCard(analyze({ step: 5, status: "published", mdrepo_published: true }))
    expect(published.container.querySelector("span.bg-primary.text-primary-foreground")).not.toBeNull()
  })

  it("shows publish details on a publish-step card", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(analyze({ step: 5, status: "published", mdrepo_published: true, mdrepo_id: "10.5281/demo" }))
    expect(screen.getByText("Published")).toBeVisible()
    expect(screen.getByText("Yes")).toBeVisible()
    expect(screen.getByText("Target")).toBeVisible()
    expect(screen.getByText("Invenio / MDRepo")).toBeVisible()
    // The opaque record id stays out of the UI; the record link belongs to the wizard publish step.
    expect(screen.queryByText("10.5281/demo")).not.toBeInTheDocument()
  })

  it("shows only the experiment source in the footer, never the MDRepo record id", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => undefined))
    await renderCard(
      analyze({
        status: "published",
        mdrepo_published: true,
        mdrepo_id: "8gahj-dh519",
        source: { type: "pdb", pdb_id: "1LYZ", files: [] },
      })
    )
    expect(screen.getByText("RCSB PDB (1LYZ)")).toBeVisible()
    expect(screen.queryByText(/8gahj/)).not.toBeInTheDocument()
  })

  it("closes the rename dialog from Cancel without a request", async () => {
    const calls: { url: string; method: string }[] = []
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: requestUrl(input), method: init?.method ?? "GET" })
      return new Response("[]", { status: 200 })
    })
    const user = userEvent.setup()
    await renderCard(analyze())
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
    await renderCard(analyze({ notebook: withNotebook("DOWN") }))
    await user.click(screen.getByRole("button", { name: "Actions for Analyze" }))
    await user.click(screen.getByRole("menuitem", { name: /start notebook/i }))
    expect(calls).toContainEqual({
      url: expect.stringContaining("/experiments/exp1/notebook"),
      method: "POST",
      body: {},
    })
  })
})
