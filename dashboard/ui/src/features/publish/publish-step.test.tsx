import type { MDPositPublication, MDRepoPublication, PublishStatus } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { requestUrl, type FetchCall } from "@/shared/fixtures/mock-fetch"
import { simulation } from "@/shared/fixtures/simulation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { afterEach, describe, expect, it, vi } from "vitest"

import { PublishStep } from "./publish-step"

const SIM = "md.simulation.json"
const DRAFT_URL = "https://mdrepo.example/uploads/rec1"

const READY_SIMULATION = simulation(SIM, {
  valid: true,
  missing_files: [],
  files: {
    reference_structure: "analysis/ref.gro",
    run_input: "production/md.tpr",
    trajectory: "production/md.xtc",
  },
})

function uploadStatus(overrides: Partial<PublishStatus> = {}): PublishStatus {
  return {
    experiment_id: "exp1",
    mdrepo_id: "rec1",
    draft_url: DRAFT_URL,
    upload_state: "running",
    reason: null,
    total_files: 5,
    completed_files: 2,
    total_bytes: 2 * 1024 ** 2,
    completed_bytes: 1024 ** 2,
    ...overrides,
  }
}

const PUBLISH_202: MDRepoPublication = {
  id: "rec1",
  links: { edit_html: DRAFT_URL },
  upload_id: "up1",
  upload_state: "queued",
  draft_url: DRAFT_URL,
}

const PUBLISH_201: MDPositPublication = {
  metadata_file: { path: "inputs.yaml", url: "/dash/api/experiments/exp1/files/download?path=inputs.yaml" },
  files: [
    { role: "structure", path: "analysis/ref.gro", url: "/dash/api/experiments/exp1/files/download?path=ref.gro" },
    { role: "topology", path: "production/md.tpr", url: "/dash/api/experiments/exp1/files/download?path=md.tpr" },
    { role: "trajectory", path: "production/md.xtc", url: "/dash/api/experiments/exp1/files/download?path=md.xtc" },
  ],
  vre_lite_url: "https://mdposit.example/vre_lite/",
}

/**
 * Stateful publish endpoints: the upload document changes over time (polling),
 * and the publish POST answers 202 (invenio) or 201 (mdposit) per request body.
 */
function mockPublish(options: { upload?: PublishStatus; authenticated?: boolean } = {}) {
  const state = { upload: options.upload ?? uploadStatus() }
  const calls: FetchCall[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    calls.push({
      url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined,
    })
    if (url.endsWith("/dash/api/mdrepo/status")) return Response.json({ authenticated: options.authenticated ?? true })
    if (url.endsWith("/experiments/exp1/publish/status")) return Response.json(state.upload)
    if (url.endsWith("/experiments/exp1/publish")) {
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as { target?: string }) : {}
      return body.target === "mdposit"
        ? Response.json(PUBLISH_201, { status: 201 })
        : Response.json(PUBLISH_202, { status: 202 })
    }
    return new Response(null, { status: 404 })
  })
  return { state, calls }
}

function renderPublish(props: Partial<React.ComponentProps<typeof PublishStep>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spies = { onStepChange: vi.fn(), onOAuthHandled: vi.fn(), ...props }
  render(
    <QueryClientProvider client={client}>
      <PublishStep experiment={experiment("exp1")} simulation={READY_SIMULATION} pollMs={25} {...spies} />
    </QueryClientProvider>
  )
  return spies
}

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState({}, "", "/")
})

describe("PublishStep MDRepo connection", () => {
  it("offers Connect to MDRepo when unauthenticated", async () => {
    mockPublish({ authenticated: false })
    renderPublish()

    expect(await screen.findByText(/one-time authorization using your e-INFRA CZ account/)).toBeInTheDocument()
    expect(screen.getByText(/redirected to MDRepo to complete the metadata/)).toBeInTheDocument()

    const connect = screen.getByRole("link", { name: /connect to mdrepo/i })
    expect(connect.getAttribute("href")).toContain("/dash/api/mdrepo/auth?")
    expect(connect.getAttribute("href")).toContain("return_url=")

    expect(screen.queryByRole("button", { name: "Publish to MDRepo" })).not.toBeInTheDocument()
  })

  it("publishes and opens the new draft when authenticated", async () => {
    const { calls } = mockPublish()
    const open = vi.spyOn(window, "open").mockImplementation(() => null)
    renderPublish()

    const user = userEvent.setup()
    await user.click(await screen.findByRole("button", { name: "Publish to MDRepo" }))

    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/publish",
        method: "POST",
        body: { target: "invenio" },
      })
    )
    await waitFor(() => expect(open).toHaveBeenCalledWith(DRAFT_URL, "_blank", "noopener,noreferrer"))
  })
})

describe("PublishStep upload states", () => {
  it("shows live progress and keeps polling until the upload completes", async () => {
    const { state } = mockPublish()
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    expect(await screen.findByText("Uploading files… (2/5)")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toBeInTheDocument()
    expect(screen.getByText("1 MB / 2 MB")).toBeInTheDocument()
    expect(screen.getByText("Uploading")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /uploading…/i })).toBeDisabled()
    expect(screen.getByText("Files:")).toBeInTheDocument()
    expect(screen.getByText("Total size:")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /view the draft in mdrepo/i })).toHaveAttribute("href", DRAFT_URL)

    state.upload = uploadStatus({ upload_state: "completed", completed_files: 5, completed_bytes: 2 * 1024 ** 2 })
    expect(await screen.findByText("Upload complete")).toBeInTheDocument()
    expect(screen.getByText("Completed")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "View in MDRepo" })).toHaveAttribute("href", DRAFT_URL)
    expect(screen.queryByRole("link", { name: /view the draft in mdrepo/i })).not.toBeInTheDocument()
  })

  it("surfaces failures with the failed file list and a retry", async () => {
    const { state, calls } = mockPublish({
      upload: uploadStatus({
        upload_state: "failed",
        reason: "source",
        failed_files: [
          { key: "production/md.xtc", error: "boom" },
          { key: "production/md.tpr", error: "boom" },
        ],
      }),
    })
    vi.spyOn(window, "open").mockImplementation(() => null)
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    expect(await screen.findByRole("alert")).toHaveTextContent(/Upload failed/)
    expect(screen.getByText("Some source files could not be read; check the files and retry.")).toBeInTheDocument()
    expect(screen.getByText("production/md.xtc")).toBeInTheDocument()
    expect(screen.getByText("2 file(s) failed to upload:")).toBeInTheDocument()

    const user = userEvent.setup()
    // The retry POST resets the upload document to a fresh active attempt.
    state.upload = uploadStatus()
    await user.click(screen.getByRole("button", { name: "Retry upload" }))
    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/publish",
        method: "POST",
        body: { target: "invenio" },
      })
    )

    expect(await screen.findByText("Uploading files… (2/5)")).toBeInTheDocument()
  })

  it("warns when a draft exists but no upload state is readable yet", async () => {
    mockPublish({
      upload: uploadStatus({
        upload_state: null,
        total_files: 0,
        completed_files: 0,
        total_bytes: 0,
        completed_bytes: 0,
      }),
    })
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    expect(await screen.findByText("A draft exists in MDRepo")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry upload" })).toBeInTheDocument()
  })
})

describe("PublishStep publication targets", () => {
  it("hides the MDPosit target for AMBER experiments", async () => {
    mockPublish()
    renderPublish({ experiment: experiment("exp1", { engine: "AMBER" }) })

    expect(await screen.findByText(/redirected to MDRepo to complete the metadata/)).toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: "Publication target" })).not.toBeInTheDocument()
  })

  it("prepares an MDPosit handoff and lists the downloads", async () => {
    const { calls } = mockPublish()
    renderPublish()

    const user = userEvent.setup()
    await user.click(await screen.findByRole("combobox", { name: "Publication target" }))
    await user.click(await screen.findByRole("option", { name: "MDPosit" }))

    expect(screen.getByText(/Stateless MDPosit handoff/)).toBeInTheDocument()
    expect(screen.getByText("MDPosit publishing workflow")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Prepare MDPosit handoff" }))
    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/publish",
        method: "POST",
        body: { target: "mdposit", simulation_path: SIM },
      })
    )

    expect(await screen.findByText("Handoff downloads")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /metadata file \(inputs\.yaml\)/i })).toHaveAttribute(
      "href",
      PUBLISH_201.metadata_file.url
    )
    expect(screen.getByRole("link", { name: /structure file/i })).toHaveAttribute("href", PUBLISH_201.files[0].url)
    expect(screen.getByRole("link", { name: /topology file/i })).toHaveAttribute("href", PUBLISH_201.files[1].url)
    expect(screen.getByRole("link", { name: /trajectory file/i })).toHaveAttribute("href", PUBLISH_201.files[2].url)
    expect(screen.getByRole("link", { name: /open vre lite/i })).toHaveAttribute("href", PUBLISH_201.vre_lite_url)
  })

  it("blocks the MDPosit handoff when the simulation misses required files", async () => {
    mockPublish()
    renderPublish({
      simulation: simulation(SIM, {
        valid: true,
        missing_files: ["trajectory"],
        files: { reference_structure: "analysis/ref.gro", run_input: "production/md.tpr" },
      }),
    })

    const user = userEvent.setup()
    await user.click(await screen.findByRole("combobox", { name: "Publication target" }))
    await user.click(await screen.findByRole("option", { name: "MDPosit" }))

    expect(await screen.findByText("Handoff unavailable")).toBeInTheDocument()
    expect(screen.getByText("Missing required files: trajectory.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Prepare MDPosit handoff" })).toBeDisabled()
  })

  it("clears a prepared handoff when the selected simulation changes", async () => {
    mockPublish()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const noop = () => undefined
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <PublishStep
          experiment={experiment("exp1")}
          simulation={READY_SIMULATION}
          pollMs={25}
          onStepChange={noop}
          onOAuthHandled={noop}
        />
      </QueryClientProvider>
    )

    const user = userEvent.setup()
    await user.click(await screen.findByRole("combobox", { name: "Publication target" }))
    await user.click(await screen.findByRole("option", { name: "MDPosit" }))
    await user.click(screen.getByRole("button", { name: "Prepare MDPosit handoff" }))
    expect(await screen.findByText("Handoff downloads")).toBeInTheDocument()

    // The wizard switches tabs without remounting the step — the previous
    // simulation's handoff must not leak into the new one.
    rerender(
      <QueryClientProvider client={client}>
        <PublishStep
          experiment={experiment("exp1")}
          simulation={simulation("other.simulation.json", {
            valid: true,
            missing_files: ["reference_structure", "run_input", "trajectory"],
            files: {},
          })}
          pollMs={25}
          onStepChange={noop}
          onOAuthHandled={noop}
        />
      </QueryClientProvider>
    )

    await waitFor(() => expect(screen.queryByText("Handoff downloads")).not.toBeInTheDocument())
  })
})

describe("PublishStep OAuth return", () => {
  it("toasts the OAuth outcome and clears the params through the router", async () => {
    window.history.replaceState({}, "", "/dash/experiments/exp1?step=4&mdrepo_auth=success")
    mockPublish()
    const spies = renderPublish()

    await waitFor(() => expect(spies.onOAuthHandled).toHaveBeenCalledTimes(1))
  })

  it("toasts the OAuth error and still clears the params", async () => {
    window.history.replaceState({}, "", "/dash/experiments/exp1?step=4&mdrepo_error=Invalid+state+parameter")
    mockPublish()
    const errorToast = vi.spyOn(toast, "error")
    const spies = renderPublish()

    await waitFor(() => expect(spies.onOAuthHandled).toHaveBeenCalledTimes(1))
    expect(errorToast).toHaveBeenCalledWith("MDRepo authentication failed: Invalid state parameter")
  })
})
