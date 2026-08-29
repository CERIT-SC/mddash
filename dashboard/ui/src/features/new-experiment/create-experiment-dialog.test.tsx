import type { Experiment } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { requestUrl } from "@/shared/fixtures/mock-fetch"
import { CATALOG_MODULES } from "@/shared/fixtures/notebook-module"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { NewExperimentPage } from "./new-experiment-page"

const NOTEBOOKS_REPO = "https://example.test/notebooks.git"

function stubApi(created: Experiment) {
  let submitted: [string, FormDataEntryValue][] | null = null
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    if (init?.method === "POST" && init.body instanceof FormData) {
      submitted = Array.from(init.body.entries())
      return Response.json(created, { status: 201 })
    }
    if (url.includes("notebook-modules")) return Response.json(CATALOG_MODULES)
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

function renderPage() {
  return renderWithProviders(
    <NewExperimentPage search={{}} onSearchChange={() => undefined} defaultNotebooksRepo={NOTEBOOKS_REPO} />
  )
}

describe("CreateExperimentDialog", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("submits a preset PDB experiment with the module of the chosen engine, then opens it", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    const { router } = await renderPage()

    await user.click(await screen.findByRole("button", { name: "Protein · AMBER" }))
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
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/experiments/new1"))
  })

  // typed round-trips need headroom past the 5s default under full-suite CPU contention
  it("validates the custom branch and submits repo, engine and DOI fields", { timeout: 15000 }, async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    await renderPage()

    await user.click(screen.getByRole("button", { name: /use custom workflow/i }))
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

    // reopening after a successful create must start from a fresh form, not stale values
    await user.click(await screen.findByRole("button", { name: /use custom workflow/i }))
    expect(screen.getByLabelText("Name")).toHaveValue("")
  })

  it("submits the git access token only for https repositories", async () => {
    const getSubmitted = stubApi(experiment("new1"))
    const user = userEvent.setup()
    await renderPage()
    await user.click(screen.getByRole("button", { name: /use custom workflow/i }))
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
    await renderPage()
    await user.click(screen.getByRole("button", { name: /use custom workflow/i }))
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
    await renderPage()

    await user.click(await screen.findByRole("button", { name: "Membrane protein (BioBB) · GROMACS" }))
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
