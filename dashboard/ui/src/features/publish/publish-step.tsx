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
import { InfoBanner } from "@/shared/ui/info-banner"
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
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
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, CloudUpload, Download, ExternalLink, Folder, HardDrive, LoaderCircle, LogIn } from "lucide-react"
import { toast } from "sonner"

import { mdpositUnavailableReason } from "./mdposit-unavailable"
import { pollWhileUploadActive, uploadActive, uploadFailureReason, uploadStateLabel } from "./upload-state"

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

/** Badge styled by upload state; completed needs the success tokens the DS Badge variants don't cover. */
function UploadStateBadge({ state }: { state: string }) {
  const variant = state === "failed" ? "error" : state === "queued" ? "secondary" : "default"
  return (
    <Badge variant={variant} className={state === "completed" ? "bg-success text-success-foreground" : undefined}>
      {uploadStateLabel(state)}
    </Badge>
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
          const url = response.data.draft_url ?? response.data.links["edit_html"] ?? response.data.links["self_html"]
          if (url !== null && url !== undefined && url !== "") window.open(url, "_blank", "noopener,noreferrer")
        },
        onError: (error) => toast.error(toApiError(error).message),
      }
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

  return (
    <>
      {completed ? (
        <Alert variant="success">
          <AlertTitle>Upload complete</AlertTitle>
          <AlertDescription>
            Your experiment data has been uploaded to the MDRepo draft. Open MDRepo to complete the metadata and
            finalize the publication.
          </AlertDescription>
        </Alert>
      ) : failed ? (
        <Alert variant="error" role="alert">
          <AlertTitle>Upload failed</AlertTitle>
          <AlertDescription>
            <p>Your draft and already-uploaded files are preserved — retry the upload to continue.</p>
            {failureReason !== null && <p className="mt-1">{failureReason}</p>}
          </AlertDescription>
        </Alert>
      ) : active ? (
        <InfoBanner>
          <AlertTitle>Upload in progress</AlertTitle>
          <AlertDescription>
            Files are being uploaded to MDRepo in the background. The draft is already openable in MDRepo, but
            incomplete until the upload finishes.
          </AlertDescription>
        </InfoBanner>
      ) : hasDraft ? (
        <Alert variant="warning">
          <AlertTitle>A draft exists in MDRepo</AlertTitle>
          <AlertDescription>View the draft in MDRepo, or retry the upload to send the files again.</AlertDescription>
        </Alert>
      ) : (
        <InfoBanner>
          <AlertTitle>Publish to MDRepo</AlertTitle>
          <AlertDescription>
            After clicking the button, you&apos;ll be redirected to MDRepo to complete the metadata and finalize the
            publication. Your files will be uploaded in the background.
          </AlertDescription>
        </InfoBanner>
      )}

      {upload !== undefined && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="flex items-center gap-2">
            <Folder className="text-text-muted h-4 w-4" aria-hidden />
            <span className="text-text-muted">Files:</span>
            {upload.total_files}
          </span>
          <span className="flex items-center gap-2">
            <HardDrive className="text-text-muted h-4 w-4" aria-hidden />
            <span className="text-text-muted">Total size:</span>
            {formatBytes(upload.total_bytes)}
          </span>
          {uploadState !== null && <UploadStateBadge state={uploadState} />}
        </div>
      )}

      {!authenticated && (
        <Alert variant="warning">
          <AlertTitle>MDRepo connection required</AlertTitle>
          <AlertDescription>
            You need to authenticate with MDRepo to{" "}
            {hasDraft ? "view or edit the published experiment" : "publish your experiment"}. This is a one-time
            authorization using your e-INFRA CZ account.
          </AlertDescription>
        </Alert>
      )}

      {active && upload !== undefined && (
        <div className="space-y-2">
          <p className="text-sm font-medium">
            {uploadState === "queued"
              ? "Upload queued — waiting for the upload job…"
              : `Uploading files… (${upload.completed_files}/${upload.total_files})`}
          </p>
          {upload.total_files > 0 && <Progress value={(upload.completed_files / upload.total_files) * 100} />}
          <p className="text-text-muted text-xs">
            {formatBytes(upload.completed_bytes)} / {formatBytes(upload.total_bytes)}
          </p>
        </div>
      )}

      {failed && (upload?.failed_files?.length ?? 0) > 0 && (
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

      {hasDraft && !completed && authenticated && recordUrl !== null && (
        <p className="text-sm">
          <Link href={recordUrl} target="_blank" rel="noreferrer">
            View the draft in MDRepo while files upload.
          </Link>
        </p>
      )}

      <Separator />

      <PublishFooter onBack={() => onStepChange(BACK_STEP)}>
        {!authenticated ? (
          <Button type="button" asChild>
            <a href={authHref}>
              <LogIn aria-hidden />
              Connect to MDRepo
            </a>
          </Button>
        ) : completed ? (
          recordUrl !== null ? (
            <Button type="button" asChild>
              <a href={recordUrl} target="_blank" rel="noreferrer">
                <ExternalLink aria-hidden />
                View in MDRepo
              </a>
            </Button>
          ) : (
            <Button type="button" disabled>
              View in MDRepo
            </Button>
          )
        ) : active || publish.isPending ? (
          <Button type="button" disabled>
            <LoaderCircle className="animate-spin" aria-hidden />
            {active ? "Uploading…" : "Publishing…"}
          </Button>
        ) : (
          <Button type="button" onClick={handlePublish}>
            <CloudUpload aria-hidden />
            {hasDraft ? "Retry upload" : "Publish to MDRepo"}
          </Button>
        )}
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

function MdpositPublish({ experiment, simulation, onStepChange }: MdpositPublishProps) {
  const prepare = usePublishExperiment()
  const handoff: MDPositPublication | undefined = prepare.data?.status === 201 ? prepare.data.data : undefined
  const unavailableReason = mdpositUnavailableReason(simulation)

  // The Stepper doesn't remount this subtree on tab switch, so drop the stale
  // handoff of the previously selected simulation before preparing a new one.
  // reset is stable across renders, so the effect re-runs only on sim change.
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

  return (
    <>
      <InfoBanner>
        <AlertTitle>Stateless MDPosit handoff</AlertTitle>
        <AlertDescription>
          This prepares a handoff package for the selected simulation. It does not change the experiment&apos;s
          publication status or wizard progress.
        </AlertDescription>
      </InfoBanner>

      {unavailableReason !== null ? (
        <Alert variant="warning">
          <AlertTitle>Handoff unavailable</AlertTitle>
          <AlertDescription>{unavailableReason}</AlertDescription>
        </Alert>
      ) : (
        <div className="text-sm">
          <p className="font-medium">MDPosit publishing workflow</p>
          <ol className="text-text-muted mt-2 list-decimal space-y-1 pl-5">
            <li>Prepare the handoff package using the button below.</li>
            <li>Download all files and open VRE Lite.</li>
            <li>Upload the metadata file (inputs.yaml) first.</li>
            <li>Review the imported form and fill in the missing fields.</li>
            <li>Upload the selected structure, topology, and trajectory files.</li>
          </ol>
        </div>
      )}

      {handoff !== undefined && (
        <div className="border-border space-y-3 rounded-md border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">Handoff downloads</p>
            {handoff.vre_lite_url !== null && handoff.vre_lite_url !== undefined && handoff.vre_lite_url !== "" && (
              <Button variant="outline" size="sm" asChild>
                <a href={handoff.vre_lite_url} target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden />
                  Open VRE Lite
                </a>
              </Button>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <HandoffDownload label="Metadata file (inputs.yaml)" file={handoff.metadata_file} />
            {handoff.files.map((file) => (
              <HandoffDownload key={file.path} label={MDPOSIT_FILE_LABELS[file.role ?? ""] ?? file.path} file={file} />
            ))}
          </div>
        </div>
      )}

      <Separator />

      <PublishFooter onBack={() => onStepChange(BACK_STEP)}>
        <Button
          type="button"
          onClick={handlePrepare}
          disabled={unavailableReason !== null || prepare.isPending}
          title={unavailableReason ?? undefined}
        >
          {prepare.isPending ? <LoaderCircle className="animate-spin" aria-hidden /> : <CloudUpload aria-hidden />}
          Prepare MDPosit handoff
        </Button>
      </PublishFooter>
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
