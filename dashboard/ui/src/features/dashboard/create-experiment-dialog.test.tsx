import type { Experiment, NotebookModule } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { CreateExperimentDialog } from "./create-experiment-dialog"

const NOTEBOOKS_REPO = "https://example.test/notebooks.git"

// Mirrors dashboard/api/notebook-modules.json: duplicate display names with
// engine-specific descriptions, so grouping and engine-dependent text are tested.
const CATALOG = {
  modules: [
    {
      id: "gromacs-protein",
      name: "Protein",
      description: "Prepare and analyze a solvated protein with GROMACS.",
      engine: "GMX",
    },
    {
      id: "amber-protein",
      name: "Protein",
      description: "Prepare a solvated protein with AMBER.",
      engine: "AMBER",
    },
    {
      id: "biobb-protein-gmx",
      name: "Protein (BioBB)",
      description: "Set up a solvated protein system using BioExcel Building Blocks and GROMACS.",
      engine: "GMX",
    },
    {
      id: "biobb-protein-amber",
      name: "Protein (BioBB)",
      description: "Set up a solvated protein system using BioExcel Building Blocks and AmberTools.",
      engine: "AMBER",
    },
    {
      id: "biobb-membrane-gmx",
      name: "Membrane protein (BioBB)",
      description: "Set up a membrane protein system using BioExcel Building Blocks and GROMACS.",
      engine: "GMX",
    },
  ] satisfies NotebookModule[],
}

function stubApi(created: Experiment) {
  let submitted: [string, FormDataEntryValue][] | null = null
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    if (init?.method === "POST" && init.body instanceof FormData) {
      submitted = Array.from(init.body.entries())
      return Response.json(created, { status: 201 })
    }
    if (url.includes("notebook-modules")) return Response.json(CATALOG.modules)
    return Response.json([])
  })
  return () => submitted
}

async function waitForSubmit(getSubmitted: () => [string, FormDataEntryValue][] | null) {
  await vi.waitFor(() => {
    if (!getSubmitted()) throw new Error("form not submitted yet")
  })
  return getSubmitted()!
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CreateExperimentDialog defaultNotebooksRepo={NOTEBOOKS_REPO} />
    </QueryClientProvider>
  )
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /new/i }))
  return await screen.findByRole("dialog")
}

describe("CreateExperimentDialog", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("lists every preset module sorted with GMX workflows first", async () => {
    stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)

    const cards = await screen.findAllByRole("button", { name: /protein/i })
    expect(cards.length).toBe(5)
    // every card carries exactly one engine chip and GMX workflows come first
    const chips = cards.map((card) => (within(card).queryByText("GROMACS") ? "GMX" : "AMBER"))
    expect(chips).toEqual(["GMX", "GMX", "GMX", "AMBER", "AMBER"])
    expect(screen.getByRole("button", { name: /custom use your own/i })).toBeVisible()
  })

  it("submits a preset PDB experiment with the module of the chosen engine", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)

    await user.click(await screen.findByRole("button", { name: /protein prepare a solvated/i }))
    // the preset fixes the engine — no engine choice to make
    expect(screen.queryByRole("radio", { name: "AMBER" })).not.toBeInTheDocument()
    await user.type(screen.getByLabelText("Name"), "Lysozyme run")
    await user.type(screen.getByLabelText(/pdb id or url/i), "1AKI")
    await user.click(screen.getByRole("button", { name: "Create Experiment" }))

    expect(await waitForSubmit(getSubmitted)).toEqual(
      expect.arrayContaining([
        ["experiment-name", "Lysozyme run"],
        ["type", "pdb"],
        ["pdb", "1AKI"],
        ["notebook-module", "amber-protein"],
        ["engine", "AMBER"],
      ])
    )
  })

  it("validates the custom branch and submits repo, engine and DOI fields", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)

    await user.click(await screen.findByRole("button", { name: /custom use your own/i }))
    expect(screen.getByRole("radio", { name: "GROMACS" })).toBeChecked()
    expect(screen.getByLabelText(/notebooks repository/i)).toHaveValue(NOTEBOOKS_REPO)

    await user.click(screen.getByRole("button", { name: "Create Experiment" }))
    expect(await screen.findByText("Enter a name for the experiment")).toBeVisible()

    await user.type(screen.getByLabelText("Name"), "Custom run")
    const repo = screen.getByLabelText(/notebooks repository/i)
    await user.clear(repo)
    await user.type(repo, "not a url")
    await user.click(screen.getByRole("button", { name: "Create Experiment" }))
    expect(await screen.findByText("Enter a valid git repository URL")).toBeVisible()

    await user.clear(repo)
    await user.type(repo, "git@github.com:lab/notebooks.git")
    await user.click(screen.getByRole("radio", { name: /doi \/ repository/i }))
    await user.type(screen.getByLabelText(/doi or repository url/i), "https://doi.org/10.5281/zenodo.1")
    await user.click(screen.getByRole("button", { name: "Create Experiment" }))

    expect(await waitForSubmit(getSubmitted)).toEqual(
      expect.arrayContaining([
        ["experiment-name", "Custom run"],
        ["type", "repo"],
        ["repo-url", "https://doi.org/10.5281/zenodo.1"],
        ["notebooks-repo", "git@github.com:lab/notebooks.git"],
        ["engine", "GMX"],
      ])
    )

    // reopening after a successful create must start from the preset picker, not the stale form
    await user.click(await screen.findByRole("button", { name: /new/i }))
    expect(await screen.findByRole("button", { name: /protein prepare and analyze/i })).toBeVisible()
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument()
  })

  it("submits the git access token only for https repositories", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)
    await user.click(await screen.findByRole("button", { name: /custom use your own/i }))
    await user.type(screen.getByLabelText("Name"), "Token run")
    await user.type(screen.getByLabelText(/pdb id or url/i), "1AKI")

    // token section is only meaningful for https — cleartext urls hide it
    expect(screen.getByText(/private repository/i)).toBeVisible()
    const repo = screen.getByLabelText(/notebooks repository/i)
    await user.clear(repo)
    await user.type(repo, "http://git.example.test/lab/notebooks.git")
    expect(screen.queryByText(/private repository/i)).not.toBeInTheDocument()

    await user.clear(repo)
    await user.type(repo, "https://example.test/notebooks.git")
    await user.click(screen.getByText(/private repository/i))
    await user.type(screen.getByLabelText(/git access token/i), "ghp_secret")
    await user.click(screen.getByRole("button", { name: "Create Experiment" }))
    expect(await waitForSubmit(getSubmitted)).toEqual(expect.arrayContaining([["access-token", "ghp_secret"]]))
  })

  it("drops a stale hidden token when the repo switches from https to ssh", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)
    await user.click(await screen.findByRole("button", { name: /custom use your own/i }))
    await user.type(screen.getByLabelText("Name"), "Token run")
    await user.type(screen.getByLabelText(/pdb id or url/i), "1AKI")

    // token entered for the default https repo…
    await user.click(screen.getByText(/private repository/i))
    await user.type(screen.getByLabelText(/git access token/i), "ghp_secret")

    // …then the repo switches to ssh: the field hides and the stale value must not leak
    const repo = screen.getByLabelText(/notebooks repository/i)
    await user.clear(repo)
    await user.type(repo, "git@github.com:lab/notebooks.git")
    expect(screen.queryByText(/private repository/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Create Experiment" }))
    const submitted = await waitForSubmit(getSubmitted)
    expect(submitted.some(([key]) => key === "access-token")).toBe(false)
  })

  it("uploads files for an engine-fixed preset", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    renderDialog()
    await openDialog(user)

    await user.click(await screen.findByRole("button", { name: /membrane protein \(biobb\)/i }))
    expect(screen.queryByRole("radio", { name: "GROMACS" })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText("Name"), "Membrane run")
    await user.click(screen.getByRole("radio", { name: /upload files/i }))
    await user.upload(
      screen.getByLabelText("Upload files"),
      new File(["x"], "topol.tpr", { type: "application/octet-stream" })
    )
    expect(await screen.findByText("topol.tpr")).toBeVisible()

    await user.click(screen.getByRole("button", { name: "Create Experiment" }))
    const submitted = await waitForSubmit(getSubmitted)
    expect(submitted).toEqual(
      expect.arrayContaining([
        ["experiment-name", "Membrane run"],
        ["type", "file"],
        ["notebook-module", "biobb-membrane-gmx"],
        ["engine", "GMX"],
      ])
    )
    const uploaded = submitted.find(([key]) => key === "simulation-files")?.[1]
    expect(uploaded).toBeInstanceOf(File)
    expect((uploaded as File).name).toBe("topol.tpr")
  })
})
