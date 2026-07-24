import { useEffect, useState } from "react"

import { useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle,
  CloudUpload,
  Download,
  ExternalLink,
  Folder,
  HardDrive,
  Info,
  Loader2,
  LogIn,
  Pencil,
} from "lucide-react"
import { toast } from "sonner"

import { DEBUG, Engine, MDPOSIT_URL } from "@/util/const"
import { formatFileSize } from "@/util/helpers"
import { simulationMdpositUnavailableReason } from "@/util/simulation"
import { type Experiment, type Simulation, type UploadState } from "@/util/types"
import { useMdPositPublishData, type MdPositHandoffFile } from "@/hooks/use-mdposit"
import { getMDRepoAuthUrl, useMDRepoStatus, usePublishExperiment, usePublishStatus } from "@/hooks/use-mdrepo"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import SimulationPreview from "@/components/Wizard/SimulationPreview"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

type PublishTarget = "invenio" | "mdposit"

const PublishStep = (props: WizardStepProps) => {
  const { experiment } = props
  const mdpositEnabled = (DEBUG || MDPOSIT_URL !== "") && experiment.engine === Engine.GMX
  const [target, setTarget] = useState<PublishTarget>("invenio")

  const handleTargetChange = (value: string) => {
    if (value === "invenio" || value === "mdposit") setTarget(value)
  }

  return (
    <div className="flex justify-center">
      <Card className={target === "invenio" ? "w-full max-w-lg" : "w-full max-w-2xl"}>
        <CardContent className="flex flex-col items-center gap-4 pt-4">
          <div className="flex items-center gap-2">
            <Info className="text-muted-foreground h-5 w-5" />
            <h2 className="text-lg font-semibold">Publish Experiment</h2>
          </div>

          {mdpositEnabled ? (
            <div className="w-full space-y-2">
              <Label htmlFor="publish-target">Publication target</Label>
              <Select value={target} onValueChange={handleTargetChange}>
                <SelectTrigger id="publish-target" className="w-full">
                  <SelectValue placeholder="Select publication target" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="invenio">Invenio / MDRepo</SelectItem>
                  <SelectItem value="mdposit">MDPosit</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {target === "invenio" || !mdpositEnabled ? (
            <InvenioPublishContent experiment={experiment} />
          ) : (
            <MdPositPublishContent experiment={experiment} selected={props.selectedSimulation} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

const InvenioPublishContent = ({ experiment }: { experiment: Experiment }) => {
  const queryClient = useQueryClient()

  const { data: mdrepoStatus } = useMDRepoStatus()
  const publishExperiment = usePublishExperiment()

  const hasDraft = experiment.mdrepo_id !== null
  const isAuthenticated = mdrepoStatus?.authenticated ?? false

  const isPolling = hasDraft && experiment.upload_state !== "completed" && experiment.upload_state !== "failed"
  const { data: publishStatus } = usePublishStatus(experiment.id, isPolling)

  const uploadState: UploadState | null = publishStatus?.upload_state ?? experiment.upload_state ?? null

  const fileCount = publishStatus?.total_files
  const totalSize = publishStatus?.total_bytes

  // Handle OAuth callback result in URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authSuccess = params.get("mdrepo_auth")
    const authError = params.get("mdrepo_error")

    if (authSuccess === "success") {
      toast.success("Successfully authenticated with MDRepo!")
      const url = new URL(window.location.href)
      url.searchParams.delete("mdrepo_auth")
      window.history.replaceState({}, "", url.toString())
    } else if (authError) {
      toast.error(`MDRepo authentication failed: ${decodeURIComponent(authError)}`)
      const url = new URL(window.location.href)
      url.searchParams.delete("mdrepo_error")
      window.history.replaceState({}, "", url.toString())
    }
  }, [])

  const handleAuthClick = () => {
    const returnUrl = window.location.href
    window.location.href = getMDRepoAuthUrl(returnUrl)
  }

  const handlePublishClick = () => {
    if (hasDraft && uploadState === "completed") {
      if (!isAuthenticated) {
        toast.error("You need to authenticate with MDRepo to view the published experiment.")
        return
      }
      window.open(experiment.mdrepo_record_url!, "_blank")
      return
    }

    publishExperiment.mutate(experiment.id, {
      onSuccess: (data) => {
        const recordUrl = data.draft_url || data.links?.edit_html || data.links?.self_html
        queryClient.setQueryData<Experiment>(["experiment", experiment.id], (old) =>
          old
            ? {
                ...old,
                mdrepo_id: data.id,
                mdrepo_record_url: recordUrl || old.mdrepo_record_url,
                upload_state: data.upload_state ?? old.upload_state,
              }
            : old
        )
        queryClient.invalidateQueries({ queryKey: ["publish", "status", experiment.id] })
        if (recordUrl) window.open(recordUrl, "_blank")
        else if (experiment.mdrepo_record_url) window.open(experiment.mdrepo_record_url, "_blank")
      },
    })
  }

  const isUploadComplete = uploadState === "completed"
  const isUploadFailed = uploadState === "failed"
  const isUploadActive = uploadState === "queued" || uploadState === "running"

  const statusFiles = publishStatus?.total_files ?? 0
  const statusCompleted = publishStatus?.completed_files ?? 0
  const statusTotalBytes = publishStatus?.total_bytes ?? 0
  const statusCompletedBytes = publishStatus?.completed_bytes ?? 0
  const progressPercent = statusFiles > 0 ? Math.round((statusCompleted / statusFiles) * 100) : 0

  return (
    <>
      {/* Status banner */}
      <div
        className={`w-full rounded-md border p-3 text-sm ${
          isUploadComplete
            ? "border-green-500 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200"
            : isUploadFailed
              ? "border-red-400 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"
              : hasDraft
                ? "border-yellow-400 bg-yellow-50 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200"
                : "border-blue-400 bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200"
        }`}
      >
        {isUploadComplete
          ? "Upload complete. Your experiment data has been published to MDRepo."
          : isUploadFailed
            ? "Upload failed. You can retry the publication — your draft and already-uploaded files are preserved."
            : hasDraft && isUploadActive
              ? "Files are being uploaded to MDRepo in the background. The draft is openable but incomplete."
              : hasDraft
                ? "A draft exists in MDRepo. Click below to view or retry the upload."
                : "Publishing will upload your experiment data to MDRepo, making it publicly accessible and citable with a DOI."}
      </div>

      {/* Stats */}
      {publishStatus && (
        <div className="flex w-full flex-col gap-2">
          <div className="flex items-center gap-2 text-sm">
            <Folder className="text-muted-foreground h-4 w-4" />
            <span className="text-muted-foreground font-medium">Files:</span>
            <span>{fileCount ?? "n/a"}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <HardDrive className="text-muted-foreground h-4 w-4" />
            <span className="text-muted-foreground font-medium">Total Size:</span>
            <span>{totalSize != null ? formatFileSize(totalSize) : "n/a"}</span>
          </div>
          {isUploadComplete && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground font-medium">Status:</span>
              <Badge className="gap-1 bg-green-500 text-xs text-white">
                <CheckCircle className="h-3 w-3" />
                Uploaded
              </Badge>
            </div>
          )}
          {isUploadFailed && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground font-medium">Status:</span>
              <Badge className="gap-1 bg-red-500 text-xs text-white">Upload Failed</Badge>
            </div>
          )}
        </div>
      )}
      {!isAuthenticated && (
        <div className="rounded-md border border-yellow-400 bg-yellow-50 p-3 text-sm text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200">
          You need to authenticate with MDRepo to{" "}
          {hasDraft ? "view or edit the published experiment" : "publish your experiment"}. This is a one-time
          authorization using your e-INFRA CZ account.
        </div>
      )}

      {/* Upload progress */}
      {isUploadActive && publishStatus && (
        <div className="w-full space-y-2 rounded-md border p-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Loader2 className="h-4 w-4 animate-spin" />
            {uploadState === "queued"
              ? "Upload queued, waiting for pod..."
              : `Uploading files... (${statusCompleted}/${statusFiles})`}
          </div>
          {statusFiles > 0 && (
            <div className="bg-muted h-2 w-full overflow-hidden rounded-full">
              <div className="h-full bg-blue-500 transition-all" style={{ width: `${progressPercent}%` }} />
            </div>
          )}
          <div className="text-muted-foreground text-xs">
            {formatFileSize(statusCompletedBytes)} / {formatFileSize(statusTotalBytes)}
          </div>
        </div>
      )}

      {/* Failed files list */}
      {isUploadFailed && publishStatus?.failed_files && publishStatus.failed_files.length > 0 && (
        <div className="w-full space-y-1 rounded-md border border-red-300 p-3 text-sm">
          <p className="font-medium">{publishStatus.failed_files.length} file(s) failed to upload:</p>
          <ul className="text-muted-foreground space-y-0.5">
            {publishStatus.failed_files.slice(0, 10).map((f, i) => (
              <li key={i} className="truncate">
                {f.key || "(general)"}
              </li>
            ))}
            {publishStatus.failed_files.length > 10 && (
              <li className="italic">...and {publishStatus.failed_files.length - 10} more</li>
            )}
          </ul>
        </div>
      )}

      {/* Action button */}
      {!isAuthenticated ? (
        <Button variant="default" size="lg" onClick={handleAuthClick} className="min-w-48">
          <LogIn className="mr-2 h-4 w-4" />
          Connect to MDRepo
        </Button>
      ) : (
        <Button
          variant="default"
          size="lg"
          onClick={handlePublishClick}
          disabled={publishExperiment.isPending || isUploadActive}
          className="min-w-48"
        >
          {publishExperiment.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : isUploadComplete ? (
            <Pencil className="mr-2 h-4 w-4" />
          ) : isUploadFailed ? (
            <CloudUpload className="mr-2 h-4 w-4" />
          ) : (
            <CloudUpload className="mr-2 h-4 w-4" />
          )}
          {isUploadComplete
            ? "View in MDRepo"
            : isUploadFailed
              ? "Retry Upload"
              : hasDraft
                ? "Retry Upload"
                : "Publish to MDRepo"}
        </Button>
      )}

      {hasDraft && !isUploadComplete && isAuthenticated && (
        <a
          href={experiment.mdrepo_record_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="text-muted-foreground hover:text-foreground text-center text-xs underline"
        >
          View the draft in MDRepo while files upload.
        </a>
      )}
    </>
  )
}

const mdpositFileLabels: Record<MdPositHandoffFile["role"] | "metadata", string> = {
  metadata: "Metadata file (inputs.yaml)",
  structure: "Structure file",
  topology: "Topology file",
  trajectory: "Trajectory file",
}

const MdPositPublishContent = ({ experiment, selected }: { experiment: Experiment; selected: Simulation | null }) => {
  const mdpositPublishData = useMdPositPublishData(experiment.id)

  const unavailableReason = simulationMdpositUnavailableReason(selected)
  const canPrepare = !!selected && !unavailableReason
  const currentHandoffData = mdpositPublishData.data

  const handlePrepareHandoff = () => {
    if (!selected) return
    mdpositPublishData.mutate(selected.simulation_path, {
      onSuccess: () => toast.success("MDPosit handoff files are ready."),
    })
  }

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="rounded-md border border-blue-400 bg-blue-50 p-3 text-sm text-blue-800 dark:bg-blue-950 dark:text-blue-200">
        Prepare a stateless MDPosit handoff package. This does not update the experiment publication status or wizard
        progress.
      </div>

      <div>
        <SimulationPreview simulation={selected ?? null} />
      </div>

      <div className="rounded-md border p-3 text-sm">
        <p className="font-medium">MDPosit publishing workflow</p>
        <ol className="text-muted-foreground mt-2 list-decimal space-y-1 pl-5">
          <li>Prepare the handoff package using the button below.</li>
          <li>Download all files and open VRE Lite.</li>
          <li>Upload the metadata file (inputs.yaml) first.</li>
          <li>Review the imported form and fill any missing fields.</li>
          <li>Upload the selected structure, topology, and trajectory files.</li>
        </ol>
      </div>

      <Button
        variant="default"
        size="lg"
        onClick={handlePrepareHandoff}
        disabled={!canPrepare || mdpositPublishData.isPending}
        className="self-center"
      >
        {mdpositPublishData.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <CloudUpload className="mr-2 h-4 w-4" />
        )}
        Prepare MDPosit handoff
      </Button>

      {!canPrepare && (
        <p className="text-muted-foreground text-center text-xs">
          {unavailableReason ?? "Select a valid simulation before preparing the MDPosit handoff."}
        </p>
      )}

      {currentHandoffData && (
        <div className="space-y-3 rounded-md border p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-medium">Handoff downloads</p>
            {currentHandoffData.vre_lite_url && (
              <Button variant="outline" size="sm" asChild>
                <a href={currentHandoffData.vre_lite_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Open VRE Lite
                </a>
              </Button>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <HandoffDownloadButton label={mdpositFileLabels.metadata} url={currentHandoffData.metadata_file.url} />
            {currentHandoffData.files.map((file) => (
              <HandoffDownloadButton key={file.role} label={mdpositFileLabels[file.role]} url={file.url} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const HandoffDownloadButton = ({ label, url }: { label: string; url: string }) => (
  <Button variant="secondary" size="sm" className="w-full justify-start" asChild>
    <a href={url} download>
      <Download className="mr-2 h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </a>
  </Button>
)

export default PublishStep
