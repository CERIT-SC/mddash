import { mockApiBySuffix, type FetchCall } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { NotebookStatusBar } from "./notebook-status-bar"

const API = "/experiments/exp1/notebook"
const SERVE = "/dash/notebook/exp1/?token=tok"

function notebook(overrides: Record<string, unknown> = {}): Response {
  return Response.json({
    id: 1,
    experiment_id: "exp1",
    token: "tok",
    tier: "1x",
    gpu: false,
    path: SERVE,
    status: "RUNNING",
    started_at: new Date(Date.now() - 5_000).toISOString(),
    ...overrides,
  })
}

function renderBar(handlers: Record<string, Response>): FetchCall[] {
  const calls = mockApiBySuffix(handlers)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <NotebookStatusBar experimentId="exp1" />
    </QueryClientProvider>
  )
  return calls
}

const region = (name: string) => screen.queryByRole("region", { name })

describe("NotebookStatusBar", () => {
  it("renders the mock's running state once the notebook serves", async () => {
    renderBar({ [API]: notebook(), [SERVE]: new Response(null, { status: 200 }) })

    expect(await screen.findByRole("region", { name: "Notebook status" })).toBeVisible()
    expect(await screen.findByText(/^[0-9]s$/)).toBeVisible()

    const open = await screen.findByRole("link", { name: "Open" })
    expect(open).toHaveAttribute("href", SERVE)
    expect(open).toHaveAttribute("target", "_blank")
    expect(screen.getByRole("button", { name: "Stop notebook" })).toBeEnabled()
  })

  it("keeps Open hidden while a RUNNING pod is not serving yet (INITIALIZING)", async () => {
    renderBar({ [API]: notebook(), [SERVE]: new Response(null, { status: 502 }) })

    expect(await screen.findByText("Initializing…")).toBeVisible()
    // Stop stays available so a slow/stuck start can be cancelled
    expect(screen.getByRole("button", { name: "Stop notebook" })).toBeEnabled()
    expect(screen.queryByRole("link", { name: "Open" })).not.toBeInTheDocument()
  })

  it("flags initialization taking longer than expected instead of fast-polling forever", async () => {
    vi.useFakeTimers()
    try {
      renderBar({ [API]: notebook(), [SERVE]: new Response(null, { status: 502 }) })
      // flush the notebook query and the first probe attempt through the fake clock
      for (let i = 0; i < 3; i++) await act(async () => await vi.advanceTimersByTimeAsync(0))
      expect(screen.getByText("Initializing…")).toBeVisible()
      // probes back off 2s→30s; past ~2 minutes of failures the label degrades
      for (let i = 0; i < 6; i++) await act(async () => await vi.advanceTimersByTimeAsync(30_000))
      expect(screen.getByText("Taking longer than expected")).toBeVisible()
    } finally {
      vi.useRealTimers()
    }
  })

  it("shows Starting… for PENDING with Stop available and no serving probe", async () => {
    const calls = renderBar({ [API]: notebook({ status: "PENDING", started_at: null }), [SERVE]: new Response(null) })

    expect(await screen.findByText("Starting…")).toBeVisible()
    expect(screen.getByRole("button", { name: "Stop notebook" })).toBeEnabled()
    expect(screen.queryByRole("link", { name: "Open" })).not.toBeInTheDocument()
    expect(calls.some((call) => call.url.includes("/dash/notebook/"))).toBe(false)
  })

  it("shows Stopping… for TERMINATING with a disabled stop button", async () => {
    renderBar({ [API]: notebook({ status: "TERMINATING" }) })

    // both the status label and the stop button read Stopping…
    expect((await screen.findAllByText("Stopping…")).length).toBe(2)
    expect(screen.getByRole("button", { name: "Stopping…" })).toBeDisabled()
    expect(screen.queryByRole("link", { name: "Open" })).not.toBeInTheDocument()
  })

  it("shows an idle placeholder for UNKNOWN with stop disabled", async () => {
    renderBar({ [API]: notebook({ status: "UNKNOWN" }) })

    expect(await screen.findByText("…")).toBeVisible()
    expect(screen.getByRole("button", { name: "Stop notebook" })).toBeDisabled()
    expect(screen.queryByRole("link", { name: "Open" })).not.toBeInTheDocument()
  })

  it("renders nothing while the notebook is DOWN", async () => {
    const calls = renderBar({ [API]: notebook({ status: "DOWN", started_at: null }) })

    await waitFor(() => expect(calls.some((call) => call.url.endsWith(API))).toBe(true))
    expect(region("Notebook status")).not.toBeInTheDocument()
  })

  it("renders nothing while the notebook query is unresolved", () => {
    renderBar({}) // every request 404s -> no notebook data

    expect(region("Notebook status")).not.toBeInTheDocument()
  })

  it("stops the notebook via the API and refetches afterwards", async () => {
    const calls = renderBar({ [API]: notebook(), [SERVE]: new Response(null, { status: 200 }) })
    await screen.findByRole("button", { name: "Stop notebook" })

    await userEvent.click(screen.getByRole("button", { name: "Stop notebook" }))

    await waitFor(() => expect(calls.some((call) => call.url.endsWith(API) && call.method === "DELETE")).toBe(true))
    // stop success invalidates and re-fetches the notebook
    await waitFor(() =>
      expect(calls.filter((call) => call.url.endsWith(API) && call.method === "GET").length).toBeGreaterThan(1)
    )
  })
})
