import type { SetupRun } from "@/api/generated/models"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SetupRunPanel } from "./setup-run"

const GET = "/experiments/exp1/setup?notebook=setup.ipynb"

async function renderPanel(run: SetupRun | null) {
  const calls = mockApiBySuffix({
    [GET]: run === null ? new Response(null, { status: 404 }) : Response.json(run),
    "/experiments/exp1/setup": Response.json({ notebook: "setup.ipynb", state: "starting" }, { status: 202 }),
  })
  const onOpenNotebook = vi.fn()
  await renderWithProviders(
    <SetupRunPanel
      experimentId="exp1"
      notebook="setup.ipynb"
      blockedReason={undefined}
      onOpenNotebook={onOpenNotebook}
    />
  )
  return { calls, onOpenNotebook }
}

afterEach(() => vi.unstubAllGlobals())

describe("SetupRunPanel", () => {
  it("runs setup with the workflow's defaults", async () => {
    const { calls } = await renderPanel(null)

    await userEvent.click(await screen.findByRole("button", { name: "Run setup" }))

    await waitFor(() => expect(calls.find((call) => call.method === "POST")?.body).toEqual({ notebook: "setup.ipynb" }))
  })

  it("follows a running setup step by step and can stop it", async () => {
    await renderPanel({ notebook: "setup.ipynb", state: "running", step: 6, total: 11, title: "Solvate" })

    expect(await screen.findByRole("status")).toHaveTextContent("Step 6 of 11 · Solvate")
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Run setup" })).not.toBeInTheDocument()
  })

  it("shows where a failed setup stopped and offers the notebook to fix it", async () => {
    const { onOpenNotebook } = await renderPanel({
      notebook: "setup.ipynb",
      state: "failed",
      step: 4,
      total: 11,
      title: "Parse the input",
      error: { step: 4, title: "Parse the input", message: "ValueError: bad residue" },
    })

    expect(await screen.findByText("Setup stopped at step 4 of 11 · Parse the input")).toBeInTheDocument()
    expect(screen.getByText("ValueError: bad residue")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Fix in notebook" }))
    expect(onOpenNotebook).toHaveBeenCalled()
  })
})
