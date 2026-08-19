import { Engine } from "@/api/generated/models"
import type { FileInfo, Simulation } from "@/api/generated/models"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { SimulationForm } from "./simulation-form"

function file(path: string, size = 1024): FileInfo {
  return { name: path.split("/").pop() ?? path, size, path, url: `/files/${path}` }
}

const TPR = file("production/protein.tpr", 353_280)
const GRO = file("analysis/protein-reference.gro", 13_700)

// The pickers poll these listings; URLSearchParams percent-encodes the ext comma.
const FILE_HANDLERS: Record<string, Response> = {
  "/experiments/exp1/files?ext=tpr": Response.json([TPR]),
  "/experiments/exp1/files?ext=gro%2Cpdb": Response.json([GRO]),
}

function renderForm(
  handlers: Record<string, Response>,
  props: Partial<React.ComponentProps<typeof SimulationForm>> = {}
) {
  const calls = mockApiBySuffix({ ...FILE_HANDLERS, ...handlers })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SimulationForm experimentId="exp1" engine={Engine.GMX} {...props} />
    </QueryClientProvider>
  )
  return calls
}

describe("SimulationForm (create, GMX)", () => {
  it("auto-fills name and output paths from the run input and gates submission on required roles", async () => {
    const user = userEvent.setup()
    renderForm({})

    const create = await screen.findByRole("button", { name: "Create simulation" })
    expect(create).toBeDisabled()
    expect(screen.getByPlaceholderText("Enter name of your choice")).toBeVisible()
    for (const section of ["Input files", "Output paths", "Runtime options"]) {
      expect(screen.getByText(section)).toBeVisible()
    }

    await user.click(screen.getByRole("combobox", { name: "Run input (.tpr)" }))
    await user.click(await screen.findByRole("option", { name: /protein\.tpr/ }))

    await vi.waitFor(() => expect(screen.getByPlaceholderText("Enter name of your choice")).toHaveValue("protein"))
    expect(screen.getByPlaceholderText("production/protein.xtc")).toHaveValue("production/protein.xtc")
    expect(screen.getByPlaceholderText("production/protein.gro")).toHaveValue("production/protein.gro")
    expect(create).toBeDisabled() // reference_structure is still required

    await user.click(screen.getByRole("combobox", { name: "Reference structure" }))
    await user.click(await screen.findByRole("option", { name: /protein-reference\.gro/ }))
    expect(create).toBeEnabled()
  })

  it("posts the manifest body and reports the created simulation", async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn()
    const created = simulation("protein.simulation.json", { name: "protein", valid: true })
    const calls = renderForm({ "/experiments/exp1/simulations": Response.json(created, { status: 201 }) }, { onSaved })

    await user.click(await screen.findByRole("combobox", { name: "Run input (.tpr)" }))
    await user.click(await screen.findByRole("option", { name: /protein\.tpr/ }))
    await user.click(screen.getByRole("combobox", { name: "Reference structure" }))
    await user.click(await screen.findByRole("option", { name: /protein-reference\.gro/ }))
    await user.click(await screen.findByRole("button", { name: "Create simulation" }))

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(created, true))
    expect(calls).toContainEqual({
      url: "/dash/api/experiments/exp1/simulations",
      method: "POST",
      body: {
        name: "protein",
        files: {
          run_input: "production/protein.tpr",
          reference_structure: "analysis/protein-reference.gro",
          trajectory: "production/protein.xtc",
          run_structure: "production/protein.gro",
        },
        extra_args: "",
      },
    })
  })

  it("disables a role picker with the mock's empty hint when no files match", async () => {
    renderForm({ "/experiments/exp1/files?ext=tpr": Response.json([]) })
    expect(await screen.findByText("No files available yet")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Run input (.tpr)" })).toBeDisabled()
  })

  it("renders the AMBER role set", async () => {
    mockApiBySuffix({})
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SimulationForm experimentId="exp1" engine={Engine.AMBER} />
      </QueryClientProvider>
    )
    expect(await screen.findByText("Topology")).toBeInTheDocument()
    expect(screen.getByText("Run control")).toBeInTheDocument()
    expect(screen.getByText("Coordinates")).toBeInTheDocument()
    expect(screen.queryByText("Run input (.tpr)")).not.toBeInTheDocument()
    expect(screen.queryByText("Final run structure")).not.toBeInTheDocument()
  })
})

describe("SimulationForm (existing manifest)", () => {
  const locked = simulation("protein.simulation.json", {
    name: "protein",
    valid: true,
    locked: true,
    step: 1,
    files: {
      run_input: "production/protein.tpr",
      reference_structure: "analysis/protein-reference.gro",
      trajectory: "production/protein.xtc",
      run_structure: "production/protein.gro",
    },
  })

  it("shows badges, disables the form, and hides save when locked", async () => {
    renderForm({}, { simulation: locked })

    expect(await screen.findByDisplayValue("protein")).toBeDisabled()
    expect(screen.getByText("GROMACS")).toBeInTheDocument()
    expect(screen.getByText("Locked")).toBeInTheDocument()
    expect(screen.getByText("Valid")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument()
    // All four roles carry "present" chips from the manifest's server-side check.
    expect(await screen.findAllByText("present")).toHaveLength(4)
  })

  it("surfaces server validation errors and keeps an unlocked repair path", async () => {
    const broken: Simulation = simulation("broken.simulation.json", {
      name: "broken",
      valid: false,
      locked: false,
      errors: ["files.run_input is required"],
      missing_files: ["run_input"],
      files: { run_input: "gone.tpr", trajectory: "production/broken.xtc" },
    })
    renderForm({}, { simulation: broken })

    expect(await screen.findByText("Invalid")).toBeInTheDocument()
    expect(screen.getByText("Manifest validation failed")).toBeInTheDocument()
    expect(screen.getByText("files.run_input is required")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument()
    // Edit mode never destroys manifest data: the vanished path stays visible as
    // a pickable "(missing)" entry, flagged by the chip, until the server says otherwise.
    const runInput = await screen.findByRole("combobox", { name: "Run input (.tpr)" })
    await vi.waitFor(() => expect(within(runInput).getByText(/gone\.tpr/)).toBeInTheDocument())
    expect(screen.getByText("missing")).toBeInTheDocument()
  })
})

describe("SimulationForm (typed name survives submit)", () => {
  it("overrides the auto-filled name with user typing and submits it", async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn()
    const created = simulation("custom.simulation.json", { name: "custom" })
    const calls = renderForm({ "/experiments/exp1/simulations": Response.json(created, { status: 201 }) }, { onSaved })

    await user.click(await screen.findByRole("combobox", { name: "Run input (.tpr)" }))
    await user.click(await screen.findByRole("option", { name: /protein\.tpr/ }))
    await user.click(screen.getByRole("combobox", { name: "Reference structure" }))
    await user.click(await screen.findByRole("option", { name: /reference\.gro/ }))

    const name = screen.getByPlaceholderText("Enter name of your choice")
    await vi.waitFor(() => expect(name).toHaveValue("protein"))
    await user.click(name)
    await user.clear(name)
    await user.type(name, "custom")

    await user.click(screen.getByRole("button", { name: "Create simulation" }))
    await vi.waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/simulations",
        method: "POST",
        body: expect.objectContaining({ name: "custom" }),
      })
    )
    expect(onSaved).toHaveBeenCalledWith(created, true)
  })
})
