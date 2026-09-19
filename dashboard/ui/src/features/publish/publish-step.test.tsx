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
function mockPublish(options: { upload?: PublishStatus; authenticated?: boolean; statusError?: number } = {}) {
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
    if (url.endsWith("/experiments/exp1/publish/status")) {
      if (options.statusError !== undefined) return Response.json({ detail: "boom" }, { status: options.statusError })
      return Response.json(state.upload)
    }
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

/** The step's marker, found via aria-current — null unless that step is active. */
function activeStepMarker(name: string) {
  return screen.getByText(name).closest("li")?.querySelector("[aria-current='step']")
}

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState({}, "", "/")
})

describe("PublishStep MDRepo connection", () => {
  it("guides through sign-in first and hides the upload action when unauthenticated", async () => {
    mockPublish({ authenticated: false })
    renderPublish()

    const guide = await screen.findByRole("region", { name: "Publish steps" })
    expect(guide).toHaveTextContent("Step by step")
    expect(guide).toHaveTextContent("First you need to sign-in with your account.")
    expect(activeStepMarker("Sign-in to MDRepo")).toBeInTheDocument()
    expect(activeStepMarker("Upload your dataset")).not.toBeInTheDocument()

    const signIn = screen.getByRole("link", { name: "Sign-in" })
    expect(signIn.getAttribute("href")).toContain("/dash/api/mdrepo/auth?")
    expect(signIn.getAttribute("href")).toContain("return_url=")

    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument()
  })

  it("publishes without opening the draft in a new tab", async () => {
    const { calls } = mockPublish()
    const open = vi.spyOn(window, "open").mockImplementation(() => null)
    renderPublish()

    const user = userEvent.setup()
    await user.click(await screen.findByRole("button", { name: "Upload" }))

    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/publish",
        method: "POST",
        body: { target: "invenio" },
      })
    )
    expect(open).not.toHaveBeenCalled()
  })
})

describe("PublishStep upload states", () => {
  it("shows live progress inside the upload step and advances the guide on completion", async () => {
    const { state } = mockPublish()
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    expect(await screen.findByText("Uploading files… (2/5)")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toBeInTheDocument()
    expect(screen.getByText("1 MB / 2 MB")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /uploading…/i })).toBeDisabled()
    expect(screen.getByText("Files")).toBeInTheDocument()
    expect(screen.getByText("Total size")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /view the draft in mdrepo/i })).toHaveAttribute("href", DRAFT_URL)
    expect(activeStepMarker("Upload your dataset")).toBeInTheDocument()

    state.upload = uploadStatus({ upload_state: "completed", completed_files: 5, completed_bytes: 2 * 1024 ** 2 })
    expect(await screen.findByRole("link", { name: "Finish in MDRepo" })).toHaveAttribute("href", DRAFT_URL)
    expect(screen.getByText(/waiting in a draft/)).toBeInTheDocument()
    expect(screen.getByLabelText("Step 1 done")).toBeInTheDocument()
    expect(screen.getByLabelText("Step 2 done")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /view the draft in mdrepo/i })).not.toBeInTheDocument()
  })

  it("surfaces failures inside the upload step with the failed file list and a retry", async () => {
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

  it("keeps sign-in the only open step when a draft exists unauthenticated", async () => {
    mockPublish({
      authenticated: false,
      upload: uploadStatus({
        upload_state: null,
        total_files: 0,
        completed_files: 0,
        total_bytes: 0,
        completed_bytes: 0,
      }),
    })
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    expect(await screen.findByRole("region", { name: "Publish steps" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Sign-in" })).toBeInTheDocument()
    expect(activeStepMarker("Sign-in to MDRepo")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Retry upload" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /view the draft in mdrepo/i })).not.toBeInTheDocument()
  })

  it("keeps sign-in done and offers finish even when the token lapses after a completed upload", async () => {
    mockPublish({
      authenticated: false,
      upload: uploadStatus({ upload_state: "completed", completed_files: 5, completed_bytes: 2 * 1024 ** 2 }),
    })
    renderPublish({ experiment: experiment("exp1", { mdrepo_id: "rec1", mdrepo_record_url: DRAFT_URL }) })

    // Nothing in-app needs the token after a completed upload; MDRepo handles its own login.
    expect(await screen.findByRole("link", { name: "Finish in MDRepo" })).toHaveAttribute("href", DRAFT_URL)
    expect(screen.getByLabelText("Step 1 done")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Sign-in" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Retry upload" })).not.toBeInTheDocument()
  })

  it("offers a retry and the draft link when a draft exists but no upload state is readable yet", async () => {
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

    expect(await screen.findByText(/A draft exists in MDRepo/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry upload" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "View the draft in MDRepo." })).toHaveAttribute("href", DRAFT_URL)
  })
})

describe("PublishStep published record", () => {
  it("shows the published card with the record link, copy action, and a disabled new-version button", async () => {
    mockPublish({
      upload: uploadStatus({ upload_state: "completed", completed_files: 5, completed_bytes: 2 * 1024 ** 2 }),
    })
    const spies = renderPublish({
      experiment: experiment("exp1", {
        mdrepo_id: "rec1",
        mdrepo_published: true,
        mdrepo_record_url: DRAFT_URL,
      }),
    })

    expect(await screen.findByText("Published")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: DRAFT_URL })).toHaveAttribute("href", DRAFT_URL)
    expect(screen.getByRole("button", { name: "Publish a new version" })).toBeDisabled()
    expect(screen.queryByRole("region", { name: "Publish steps" })).not.toBeInTheDocument()
    expect(await screen.findByText("Files")).toBeInTheDocument()
    expect(screen.getByText("Total size")).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "Copy record link" }))
    expect(await navigator.clipboard.readText()).toBe(DRAFT_URL)

    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(spies.onStepChange).toHaveBeenCalledWith(3)
  })

  it("keeps the card visible but surfaces a stats fetch failure with a retry", async () => {
    mockPublish({ statusError: 500 })
    renderPublish({
      experiment: experiment("exp1", {
        mdrepo_id: "rec1",
        mdrepo_published: true,
        mdrepo_record_url: DRAFT_URL,
      }),
    })

    expect(await screen.findByText("Published")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: DRAFT_URL })).toHaveAttribute("href", DRAFT_URL)
    expect(await screen.findByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("Files")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Publish a new version" })).toBeDisabled()
  })
})

describe("PublishStep publication targets", () => {
  it("hides the MDPosit target for AMBER experiments", async () => {
    mockPublish()
    renderPublish({ experiment: experiment("exp1", { engine: "AMBER" }) })

    expect(await screen.findByRole("button", { name: "Upload" })).toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: "Publication target" })).not.toBeInTheDocument()
  })

  it("guides the MDPosit handoff through prepare, download, and VRE Lite steps", async () => {
    const { calls } = mockPublish()
    renderPublish()

    const user = userEvent.setup()
    await user.click(await screen.findByRole("combobox", { name: "Publication target" }))
    await user.click(await screen.findByRole("option", { name: "MDPosit" }))

    const guide = await screen.findByRole("region", { name: "MDPosit steps" })
    expect(guide).toHaveTextContent(/doesn't change the experiment's publication status or wizard progress/)
    expect(activeStepMarker("Prepare the handoff package")).toBeInTheDocument()
    expect(activeStepMarker("Finish deposition in VRE Lite")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Prepare MDPosit handoff" }))
    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/dash/api/experiments/exp1/publish",
        method: "POST",
        body: { target: "mdposit", simulation_path: SIM },
      })
    )

    expect(await screen.findByLabelText("Step 1 done")).toBeInTheDocument()
    // Download and finish both open once the package exists (off-platform flow).
    expect(activeStepMarker("Download the handoff files")).toBeInTheDocument()
    expect(activeStepMarker("Finish deposition in VRE Lite")).toBeInTheDocument()
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
    expect(await screen.findByRole("link", { name: /metadata file \(inputs\.yaml\)/i })).toBeInTheDocument()

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

    await waitFor(() =>
      expect(screen.queryByRole("link", { name: /metadata file \(inputs\.yaml\)/i })).not.toBeInTheDocument()
    )
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
