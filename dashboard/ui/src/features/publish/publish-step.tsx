import { useEffect, useRef, useState, type ReactNode } from "react"

import { toApiError } from "@/api/errors"
import {
  getAuthorizeMDRepoUrl,
  getGetExperimentQueryKey,
  getGetPublishStatusQueryKey,
  useGetMDRepoStatus,
  useGetPublishStatus,
  usePublishExperiment,
} from "@/api/generated/client"
import {
  Engine,
  PublishRequestTarget,
  type Experiment,
  type MDPositPublication,
  type PublicationFile,
  type PublishStatus,
  type Simulation,
} from "@/api/generated/models"
import { formatBytes } from "@/shared/format"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { StepGuide, type StepGuideState, type StepGuideStep } from "@/shared/ui/step-guide"
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  H4,
  Label,
  Link,
  Progress,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
  Small,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  CloudUpload,
  Copy,
  Download,
  ExternalLink,
  Folder,
  HardDrive,
  LoaderCircle,
  LogIn,
  Plus,
} from "lucide-react"
import { toast } from "sonner"

import { mdpositUnavailableReason } from "./mdposit-unavailable"
import { pollWhileUploadActive, uploadActive, uploadFailureReason } from "./upload-state"

const PUBLISH_POLL_MS = 3000
const BACK_STEP = 3
const MAX_FAILED_LISTED = 10

type PublishStepProps = {
  experiment: Experiment
  simulation: Simulation
  onStepChange: (step: number) => void
  /** Drops the transient MDRepo OAuth params from the URL through the router. */
  onOAuthHandled: () => void
  /** Test seam; production callers omit it. */
  pollMs?: number
}

/** Publish wizard step: MDRepo draft upload with background Job progress, or an MDPosit handoff package. */
export function PublishStep({ experiment, simulation, onStepChange, onOAuthHandled, pollMs }: PublishStepProps) {
  const mdpositEnabled = experiment.engine === Engine.GMX
  const [target, setTarget] = useState<PublishRequestTarget>(PublishRequestTarget.invenio)

  // The MDRepo OAuth callback returns here with ?mdrepo_auth/?mdrepo_error —
  // toast the outcome, then drop the params so a refresh can't re-toast.
  const handledRef = useRef(false)
  useEffect(() => {
    if (handledRef.current) return
    const params = new URLSearchParams(window.location.search)
    const auth = params.get("mdrepo_auth")
    const error = params.get("mdrepo_error")
    if (auth === null && error === null) return
    handledRef.current = true
    if (auth === "success") toast.success("Successfully authenticated with MDRepo.")
    if (error !== null) toast.error(`MDRepo authentication failed: ${error}`)
    onOAuthHandled()
  }, [onOAuthHandled])

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <H4>Publish your experiment (optional)</H4>
        <p className="text-text-muted text-sm">
          Upload the experiment&apos;s data to a public repository to make it citable, or hand it off to MDPosit.
        </p>
      </div>

      {mdpositEnabled && (
        <div className="max-w-72 space-y-2">
          <Label htmlFor="publish-target">Publication target</Label>
          <Select value={target} onValueChange={(value) => setTarget(value as PublishRequestTarget)}>
            <SelectTrigger id="publish-target" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PublishRequestTarget.invenio}>Invenio / MDRepo</SelectItem>
              <SelectItem value={PublishRequestTarget.mdposit}>MDPosit</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {target === PublishRequestTarget.mdposit ? (
        <MdpositPublish experiment={experiment} simulation={simulation} onStepChange={onStepChange} />
      ) : (
        <InvenioPublish experiment={experiment} onStepChange={onStepChange} pollMs={pollMs ?? PUBLISH_POLL_MS} />
      )}
    </div>
  )
}

/** Dataset totals; only known once the upload status document exists. */
function PublishStats({ upload }: { upload: PublishStatus }) {
  return (
    <div className="flex flex-wrap gap-x-12 gap-y-2">
      <div>
        <p className="text-text-muted flex items-center gap-2 text-sm">
          <Folder className="h-4 w-4" aria-hidden />
          Files
        </p>
        <p className="text-sm font-medium">{upload.total_files}</p>
      </div>
      <div>
        <p className="text-text-muted flex items-center gap-2 text-sm">
          <HardDrive className="h-4 w-4" aria-hidden />
          Total size
        </p>
        <p className="text-sm font-medium">{formatBytes(upload.total_bytes)}</p>
      </div>
    </div>
  )
}

type InvenioPublishProps = {
  experiment: Experiment
  onStepChange: (step: number) => void
  pollMs: number
}

function InvenioPublish({ experiment, onStepChange, pollMs }: InvenioPublishProps) {
  const queryClient = useQueryClient()
  const experimentId = experiment.id

  const mdrepoStatus = useGetMDRepoStatus({ query: { retry: false } })
  const publish = usePublishExperiment()

  // mdrepo_id is NullableString — treat both null and undefined as absent.
  const hasDraft = experiment.mdrepo_id !== null && experiment.mdrepo_id !== undefined
  const published = experiment.mdrepo_published === true
  const authenticated = mdrepoStatus.data?.status === 200 && mdrepoStatus.data.data.authenticated

  // The upload status document only exists once a draft has been created.
  const uploadQuery = useGetPublishStatus(experimentId, {
    query: { enabled: hasDraft, retry: false, refetchInterval: pollWhileUploadActive(pollMs) },
  })
  const upload: PublishStatus | undefined = uploadQuery.data?.status === 200 ? uploadQuery.data.data : undefined
  const uploadState = upload?.upload_state ?? null
  const active = uploadActive(uploadState)
  const completed = uploadState === "completed"
  const failed = uploadState === "failed"

  const recordUrl = upload?.draft_url ?? experiment.mdrepo_record_url ?? null
  const failureReason = uploadFailureReason(upload?.reason)
  // Captured at render; the wizard URL (simulation + step) round-trips through the
  // OAuth callback. Must stay a relative path — the API rejects absolute return_urls.
  const authHref = getAuthorizeMDRepoUrl({ return_url: `${window.location.pathname}${window.location.search}` })

  const handlePublish = () => {
    publish.mutate(
      { experimentId, data: { target: PublishRequestTarget.invenio } },
      {
        onSuccess: (response) => {
          if (response.status !== 202) return
          void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
          void queryClient.invalidateQueries({ queryKey: getGetPublishStatusQueryKey(experimentId) })
        },
        onError: (error) => toast.error(toApiError(error).message),
      }
    )
  }

  // A published record skips the guide and never gates on the connection check below.
  if (published) {
    return (
      <PublishedRecord
        recordUrl={recordUrl}
        upload={upload}
        uploadError={hasDraft && uploadQuery.isError ? uploadQuery.error : undefined}
        onRetryStats={() => void uploadQuery.refetch()}
        onBack={() => onStepChange(BACK_STEP)}
      />
    )
  }

  if (mdrepoStatus.isError) {
    return (
      <>
        <ApiErrorAlert error={mdrepoStatus.error} onRetry={() => void mdrepoStatus.refetch()} />
        <PublishFooter onBack={() => onStepChange(BACK_STEP)} />
      </>
    )
  }

  if (mdrepoStatus.isPending) {
    return (
      <>
        <Skeleton className="h-16 w-full" />
        <PublishFooter onBack={() => onStepChange(BACK_STEP)} busy />
      </>
    )
  }

  if (hasDraft && uploadQuery.isError) {
    return (
      <>
        <ApiErrorAlert error={uploadQuery.error} onRetry={() => void uploadQuery.refetch()} />
        <PublishFooter onBack={() => onStepChange(BACK_STEP)} />
      </>
    )
  }

  // A completed upload voids sign-in: nothing in-app needs the token afterwards.
  const signIn: StepGuideState = authenticated || completed ? "done" : "active"
  const uploadStep: StepGuideState = completed ? "done" : authenticated ? "active" : "pending"
  const finish: StepGuideState = completed ? "active" : "pending"

  const steps: StepGuideStep[] = [
    {
      title: "Sign-in to MDRepo",
      state: signIn,
      body:
        signIn === "active" ? (
          <>
            <Small>First you need to sign-in with your account.</Small>
            <div>
              <Button type="button" asChild>
                <a href={authHref}>
                  <LogIn aria-hidden />
                  Sign-in
                </a>
              </Button>
            </div>
          </>
        ) : null,
    },
    {
      title: "Upload your dataset",
      state: uploadStep,
      body:
        uploadStep === "active" ? (
          <>
            {failed ? (
              <>
                <Alert variant="error" role="alert">
                  <AlertTitle>Upload failed</AlertTitle>
                  <AlertDescription>
                    <p>Your draft and uploaded files are preserved. Retry the upload to continue.</p>
                    {failureReason !== null && <p className="mt-1">{failureReason}</p>}
                  </AlertDescription>
                </Alert>
                {(upload?.failed_files?.length ?? 0) > 0 && (
                  <div className="border-border space-y-1 rounded-md border p-4 text-sm">
                    <p className="font-medium">{upload?.failed_files?.length} file(s) failed to upload:</p>
                    <ul className="text-text-muted space-y-0.5">
                      {upload?.failed_files?.slice(0, MAX_FAILED_LISTED).map((file) => (
                        <li key={file.key} className="truncate" title={file.error}>
                          {file.key}
                        </li>
                      ))}
                      {(upload?.failed_files?.length ?? 0) > MAX_FAILED_LISTED && (
                        <li className="italic">…and {(upload?.failed_files?.length ?? 0) - MAX_FAILED_LISTED} more</li>
                      )}
                    </ul>
                  </div>
                )}
              </>
            ) : active && upload !== undefined ? (
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  {uploadState === "queued"
                    ? "Upload queued. Waiting for the upload job…"
                    : `Uploading files… (${upload.completed_files}/${upload.total_files})`}
                </p>
                {upload.total_files > 0 && <Progress value={(upload.completed_files / upload.total_files) * 100} />}
                <p className="text-text-muted text-xs">
                  {formatBytes(upload.completed_bytes)} / {formatBytes(upload.total_bytes)}
                </p>
              </div>
            ) : (
              <Small>
                {hasDraft
                  ? "A draft exists in MDRepo — retry the upload to update it, or finish the deposition there."
                  : "This step is going to upload your data to MDRepo server."}
              </Small>
            )}

            {hasDraft && recordUrl !== null && (
              <p className="text-sm">
                <Link href={recordUrl} target="_blank" rel="noreferrer">
                  {active ? "View the draft in MDRepo while files upload." : "View the draft in MDRepo."}
                </Link>
              </p>
            )}

            <div>
              {active || publish.isPending ? (
                <Button type="button" disabled>
                  <LoaderCircle className="animate-spin" aria-hidden />
                  {active ? "Uploading…" : "Publishing…"}
                </Button>
              ) : (
                <Button type="button" onClick={handlePublish}>
                  <CloudUpload aria-hidden />
                  {hasDraft ? "Retry upload" : "Upload"}
                </Button>
              )}
            </div>
          </>
        ) : null,
    },
    {
      title: "Finish deposition in MDRepo",
      state: finish,
      body:
        finish === "active" ? (
          <>
            <Small>
              Your files are uploaded and waiting in a draft. Fill in the metadata there to publish — you don&apos;t
              need to come back here.
            </Small>
            <div>
              {recordUrl !== null ? (
                <Button type="button" asChild>
                  <a href={recordUrl} target="_blank" rel="noreferrer">
                    <ExternalLink aria-hidden />
                    Finish in MDRepo
                  </a>
                </Button>
              ) : (
                <Button type="button" disabled>
                  Finish in MDRepo
                </Button>
              )}
            </div>
          </>
        ) : null,
    },
  ]

  return (
    <>
      {upload !== undefined && <PublishStats upload={upload} />}
      <StepGuide title="Step by step" label="Publish steps" steps={steps} />
      <Separator />
      <PublishFooter onBack={() => onStepChange(BACK_STEP)} />
    </>
  )
}

type PublishedRecordProps = {
  recordUrl: string | null
  upload: PublishStatus | undefined
  /** Set when the status document can't be read; replaces the stats it would feed. */
  uploadError?: unknown
  onRetryStats?: () => void
  onBack: () => void
}

/** The terminal state: the record is public on MDRepo, so nothing here is actionable. */
function PublishedRecord({ recordUrl, upload, uploadError, onRetryStats, onBack }: PublishedRecordProps) {
  const copyRecordLink = () => {
    if (recordUrl === null) return
    void navigator.clipboard.writeText(recordUrl).then(
      () => toast.success("Record link copied."),
      () => toast.error("Couldn't copy the record link.")
    )
  }

  return (
    <>
      <Alert variant="success">
        <AlertTitle>Published</AlertTitle>
        <AlertDescription>This experiment is published on MDRepo and can be cited from there.</AlertDescription>
      </Alert>

      <div className="border-border space-y-4 rounded-md border p-4">
        <div className="space-y-1">
          <p className="text-text-muted text-sm">MDRepo record</p>
          {recordUrl !== null ? (
            <div className="flex items-center gap-2">
              <Link href={recordUrl} target="_blank" rel="noreferrer" className="truncate">
                {recordUrl}
              </Link>
              <Button type="button" variant="ghost" size="icon" aria-label="Copy record link" onClick={copyRecordLink}>
                <Copy aria-hidden />
              </Button>
            </div>
          ) : (
            <p className="text-sm">The record URL isn&apos;t available.</p>
          )}
        </div>
        {uploadError !== undefined ? (
          <ApiErrorAlert error={uploadError} onRetry={onRetryStats} />
        ) : upload !== undefined ? (
          <>
            <Separator />
            <PublishStats upload={upload} />
          </>
        ) : null}
      </div>

      <Separator />

      <PublishFooter onBack={onBack}>
        {/* Disabled: the API rejects re-publishing a published record; span keeps the tooltip reachable. */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-not-allowed" tabIndex={0}>
              <Button type="button" disabled className="pointer-events-none">
                <Plus aria-hidden />
                Publish a new version
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>Publishing a new version of a published record isn&apos;t supported yet.</TooltipContent>
        </Tooltip>
      </PublishFooter>
    </>
  )
}

const MDPOSIT_FILE_LABELS: Record<string, string> = {
  structure: "Structure file",
  topology: "Topology file",
  trajectory: "Trajectory file",
}

type MdpositPublishProps = {
  experiment: Experiment
  simulation: Simulation
  onStepChange: (step: number) => void
}

/** MDPosit handoff is stateless: once the package is prepared, download and finish are both open (off-platform). */
function MdpositPublish({ experiment, simulation, onStepChange }: MdpositPublishProps) {
  const prepare = usePublishExperiment()
  const handoff: MDPositPublication | undefined = prepare.data?.status === 201 ? prepare.data.data : undefined
  const unavailableReason = mdpositUnavailableReason(simulation)

  // No remount on tab switch: reset the previous simulation's stale handoff
  // before preparing a new one (reset is stable — re-runs only on sim change).
  const { reset } = prepare
  useEffect(() => {
    reset()
  }, [simulation.simulation_path, reset])

  const handlePrepare = () => {
    if (unavailableReason !== null) return
    prepare.mutate(
      {
        experimentId: experiment.id,
        data: { target: PublishRequestTarget.mdposit, simulation_path: simulation.simulation_path },
      },
      {
        onSuccess: (response) => {
          if (response.status === 201) toast.success("MDPosit handoff files are ready.")
        },
        onError: (error) => toast.error(toApiError(error).message),
      }
    )
  }

  const packageStep: StepGuideState = handoff !== undefined ? "done" : "active"
  const afterPrepare: StepGuideState = handoff !== undefined ? "active" : "pending"
  const vreLiteUrl = handoff?.vre_lite_url

  const steps: StepGuideStep[] = [
    {
      title: "Prepare the handoff package",
      state: packageStep,
      body:
        packageStep === "active" ? (
          <>
            <Small>
              Packages the selected simulation&apos;s files for MDPosit. This doesn&apos;t change the experiment&apos;s
              publication status or wizard progress.
            </Small>
            {unavailableReason !== null && (
              <Alert variant="warning">
                <AlertTitle>Handoff unavailable</AlertTitle>
                <AlertDescription>{unavailableReason}</AlertDescription>
              </Alert>
            )}
            <div>
              <Button
                type="button"
                onClick={handlePrepare}
                disabled={unavailableReason !== null || prepare.isPending}
                title={unavailableReason ?? undefined}
              >
                {prepare.isPending ? (
                  <LoaderCircle className="animate-spin" aria-hidden />
                ) : (
                  <CloudUpload aria-hidden />
                )}
                Prepare MDPosit handoff
              </Button>
            </div>
          </>
        ) : null,
    },
    {
      title: "Download the handoff files",
      state: afterPrepare,
      body:
        handoff !== undefined ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <HandoffDownload label="Metadata file (inputs.yaml)" file={handoff.metadata_file} />
            {handoff.files.map((file) => (
              <HandoffDownload key={file.path} label={MDPOSIT_FILE_LABELS[file.role ?? ""] ?? file.path} file={file} />
            ))}
          </div>
        ) : null,
    },
    {
      title: "Finish deposition in VRE Lite",
      state: afterPrepare,
      body:
        handoff !== undefined ? (
          <>
            <Small>
              Open VRE Lite, upload the metadata file (inputs.yaml) first, review the imported form, then upload the
              structure, topology, and trajectory files. The deposition finishes outside MDDash — you don&apos;t need to
              come back here.
            </Small>
            <div>
              {typeof vreLiteUrl === "string" && vreLiteUrl !== "" ? (
                <Button type="button" asChild>
                  <a href={vreLiteUrl} target="_blank" rel="noreferrer">
                    <ExternalLink aria-hidden />
                    Open VRE Lite
                  </a>
                </Button>
              ) : (
                <Button type="button" disabled>
                  Open VRE Lite
                </Button>
              )}
            </div>
          </>
        ) : null,
    },
  ]

  return (
    <>
      <StepGuide title="Step by step" label="MDPosit steps" steps={steps} />
      <Separator />
      <PublishFooter onBack={() => onStepChange(BACK_STEP)} />
    </>
  )
}

function HandoffDownload({ label, file }: { label: string; file: PublicationFile }) {
  return (
    <Button variant="secondary" size="sm" className="justify-start" asChild>
      <a href={file.url} download>
        <Download className="shrink-0" aria-hidden />
        <span className="truncate">{label}</span>
      </a>
    </Button>
  )
}

type PublishFooterProps = {
  onBack: () => void
  /** Renders a disabled working-state primary (initial connection check). */
  busy?: boolean
  children?: ReactNode
}

function PublishFooter({ onBack, busy = false, children }: PublishFooterProps) {
  return (
    <div className="flex items-center justify-end gap-2">
      <Button type="button" variant="outline" onClick={onBack}>
        <ArrowLeft aria-hidden />
        Back
      </Button>
      {busy ? (
        <Button type="button" disabled>
          <LoaderCircle className="animate-spin" aria-hidden />
          Checking MDRepo…
        </Button>
      ) : (
        children
      )}
    </div>
  )
}
