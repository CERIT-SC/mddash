import type { Experiment } from "@/api/generated/models"
import { experiment, withNotebook } from "@/shared/fixtures/experiment"
import { mockNotebookQuotaApi } from "@/shared/fixtures/notebook-quota"
import { renderWithProviders } from "@/shared/fixtures/render-with-providers"
import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { NotebookQuotaDialog, type PendingNotebookStart } from "./notebook-quota-dialog"

const PENDING: PendingNotebookStart = { experimentId: "exp1", data: { tier: "2x", gpu: true } }

function twoRunning(): Experiment[] {
  return [
    experiment("exp1", { name: "test", notebook: withNotebook("RUNNING", "exp1") }),
    experiment("exp2", { name: "Experiment no.2", notebook: withNotebook("RUNNING", "exp2") }),
    experiment("exp3", { name: "Idle", notebook: withNotebook("DOWN", "exp3") }),
  ]
}

async function renderDialog(onOpenChange = vi.fn()) {
  await renderWithProviders(<NotebookQuotaDialog open onOpenChange={onOpenChange} pendingStart={PENDING} />)
  return onOpenChange
}

describe("NotebookQuotaDialog", () => {
  it("lists running notebooks with the pending start disabled while the limit is full", async () => {
    mockNotebookQuotaApi({ limit: 2, experiments: twoRunning() })
    await renderDialog()

    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText("Notebook limit reached")).toBeVisible()
    expect(within(dialog).getByText(/stop one of your notebooks to free a slot/i)).toBeVisible()
    expect(await within(dialog).findByText("2/2")).toBeVisible()

    expect(await within(dialog).findByText("test")).toBeVisible()
    expect(within(dialog).getByText("Experiment no.2")).toBeVisible()
    expect(within(dialog).queryByText("Idle")).not.toBeInTheDocument()

    expect(within(dialog).getByRole("link", { name: "Open notebook for test" })).toBeInTheDocument()
    expect(within(dialog).getByRole("button", { name: "Stop notebook for Experiment no.2" })).toBeEnabled()
    expect(within(dialog).getByRole("button", { name: "Start new notebook" })).toBeDisabled()
  })

  it("reads as ready after stopping a notebook and retries the original start request", async () => {
    const { calls } = mockNotebookQuotaApi({ limit: 2, experiments: twoRunning() })
    const onOpenChange = await renderDialog()
    const user = userEvent.setup()

    const dialog = await screen.findByRole("dialog")
    await user.click(await within(dialog).findByRole("button", { name: "Stop notebook for Experiment no.2" }))
    expect(calls).toContainEqual({ url: "/dash/api/experiments/exp2/notebook", method: "DELETE", body: undefined })

    expect(await within(dialog).findByText("Ready to start")).toBeVisible()
    expect(await within(dialog).findByText("Stopped")).toBeVisible()
    expect(within(dialog).getByText("1/2")).toBeVisible()

    const start = within(dialog).getByRole("button", { name: "Start new notebook" })
    expect(start).toBeEnabled()
    await user.click(start)
    expect(calls).toContainEqual({
      url: "/dash/api/experiments/exp1/notebook",
      method: "POST",
      body: { tier: "2x", gpu: true },
    })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("shows the problem details durably when the retried start is rejected again", async () => {
    mockNotebookQuotaApi({ limit: 2, experiments: twoRunning(), startFails: true })
    const onOpenChange = await renderDialog()
    const user = userEvent.setup()

    const dialog = await screen.findByRole("dialog")
    await user.click(await within(dialog).findByRole("button", { name: "Stop notebook for Experiment no.2" }))
    await user.click(await within(dialog).findByRole("button", { name: "Start new notebook" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("urn:mddash:notebook-quota-exceeded")
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it("keeps the start disabled while the running list is still loading", async () => {
    mockNotebookQuotaApi({ limit: 2, experiments: twoRunning(), listNeverResolves: true })
    await renderDialog()

    const dialog = await screen.findByRole("dialog")
    expect(await within(dialog).findByText("…/2")).toBeVisible()
    expect(within(dialog).getByRole("button", { name: "Start new notebook" })).toBeDisabled()
  })
})
