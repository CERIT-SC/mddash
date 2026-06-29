import { useEffect, useMemo, useState } from "react"

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

import { formatFileSize } from "@/util/helpers"
import { type Experiment } from "@/util/types"
import { useFiles } from "@/hooks/use-files"
import { useMdPositPublishData, type MdPositHandoffFile, type MdPositSelectedFiles } from "@/hooks/use-mdposit"
import { getMDRepoAuthUrl, useMDRepoStatus, usePublishExperiment } from "@/hooks/use-mdrepo"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import FileSelector from "@/components/FileSelector"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

type PublishTarget = "invenio" | "mdposit"

const PublishStep = (props: WizardStepProps) => {
  const { experiment } = props
  const [target, setTarget] = useState<PublishTarget>("invenio")

  const handleTargetChange = (value: string) => {
    if (value === "invenio" || value === "mdposit") setTarget(value)
  }

  return (
    <div className="flex justify-center p-6">
      <Card className={target === "invenio" ? "w-full max-w-lg" : "w-full max-w-2xl"}>
        <CardContent className="flex flex-col items-center gap-4 pt-4">
          <div className="flex items-center gap-2">
            <Info className="text-muted-foreground h-5 w-5" />
            <h2 className="text-lg font-semibold">Publish Experiment</h2>
          </div>

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

          {target === "invenio" ? (
            <InvenioPublishContent experiment={experiment} />
          ) : (
            <MdPositPublishContent experiment={experiment} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

const InvenioPublishContent = ({ experiment }: { experiment: Experiment }) => {
  const queryClient = useQueryClient()

  const { data: mdrepoStatus, isLoading: loadingAuth } = useMDRepoStatus()
  const { data: files = [], isLoading: loadingFiles } = useFiles(experiment.id)
  const publishExperiment = usePublishExperiment()

  const isAuthenticated = mdrepoStatus?.authenticated ?? false
  const isPublished = experiment.mdrepo_id !== null
  const isLoading = loadingAuth || loadingFiles

  const fileCount = files.length
  const totalSize = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files])

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
    if (isPublished) {
      if (!isAuthenticated) {
        toast.error("You need to authenticate with MDRepo to view the published experiment.")
        return
      }
      window.open(experiment.mdrepo_record_url!, "_blank")
      return
    }

    publishExperiment.mutate(experiment.id, {
      onSuccess: (data) => {
        const recordUrl = data.links?.edit_html || data.links?.self_html
        queryClient.setQueryData<Experiment>(["experiment", experiment.id], (old) =>
          old
            ? {
                ...old,
                mdrepo_id: data.id,
                mdrepo_record_url: recordUrl || old.mdrepo_record_url,
              }
            : old
        )
        if (recordUrl) window.open(recordUrl, "_blank")
        else if (experiment.mdrepo_record_url) window.open(experiment.mdrepo_record_url, "_blank")
      },
    })
  }

  return (
    <>
      {/* Status banner */}
      <div
        className={`w-full rounded-md border p-3 text-sm ${
          isPublished
            ? "border-green-500 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200"
            : "border-blue-400 bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200"
        }`}
      >
        {isPublished
          ? "This experiment is already published to MDRepo. Click below to view or edit the published version."
          : "Publishing will upload your experiment data to MDRepo, making it publicly accessible and citable with a DOI."}
      </div>

      {/* Stats */}
      {isLoading ? (
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading...
        </div>
      ) : (
        <div className="flex w-full flex-col gap-2">
          <div className="flex items-center gap-2 text-sm">
            <Folder className="text-muted-foreground h-4 w-4" />
            <span className="text-muted-foreground font-medium">Files:</span>
            <span>{fileCount}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <HardDrive className="text-muted-foreground h-4 w-4" />
            <span className="text-muted-foreground font-medium">Total Size:</span>
            <span>{formatFileSize(totalSize)}</span>
          </div>
          {isPublished && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground font-medium">Status:</span>
              <Badge className="gap-1 bg-green-500 text-xs text-white">
                <CheckCircle className="h-3 w-3" />
                Published
              </Badge>
            </div>
          )}
          {!isAuthenticated && (
            <div className="rounded-md border border-yellow-400 bg-yellow-50 p-3 text-sm text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200">
              You need to authenticate with MDRepo to{" "}
              {isPublished ? "view or edit the published experiment" : "publish your experiment"}. This is a one-time
              authorization using your e-INFRA CZ account.
            </div>
          )}
        </div>
      )}

      {/* Action button */}
      {!isAuthenticated ? (
        <Button variant="default" size="lg" onClick={handleAuthClick} disabled={isLoading} className="min-w-48">
          <LogIn className="mr-2 h-4 w-4" />
          Connect to MDRepo
        </Button>
      ) : (
        <Button
          variant="default"
          size="lg"
          onClick={handlePublishClick}
          disabled={publishExperiment.isPending || isLoading}
          className="min-w-48"
        >
          {publishExperiment.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : isPublished ? (
            <Pencil className="mr-2 h-4 w-4" />
          ) : (
            <CloudUpload className="mr-2 h-4 w-4" />
          )}
          {isPublished ? "View in MDRepo" : "Publish to MDRepo"}
        </Button>
      )}

      {!isPublished && isAuthenticated && (
        <p className="text-muted-foreground text-center text-xs">
          After clicking the button, you'll be redirected to MDRepo to complete the metadata and finalize the
          publication. Your files will be uploaded in the background.
        </p>
      )}
    </>
  )
}

const mdpositSelectedDefaults: MdPositSelectedFiles = {
  structure: "",
  topology: "",
  trajectory: "",
}

const mdpositFileLabels: Record<MdPositHandoffFile["role"] | "metadata", string> = {
  metadata: "Metadata file (inputs.yaml)",
  structure: "Structure file",
  topology: "Topology file",
  trajectory: "Trajectory file",
}

const MdPositPublishContent = ({ experiment }: { experiment: Experiment }) => {
  const [selectedFiles, setSelectedFiles] = useState<MdPositSelectedFiles>({ ...mdpositSelectedDefaults })
  const [handoffFiles, setHandoffFiles] = useState<MdPositSelectedFiles | null>(null)
  const mdpositPublishData = useMdPositPublishData(experiment.id)

  const selectedCount = Object.values(selectedFiles).filter(Boolean).length
  const canPrepareHandoff = selectedCount === 3
  const isHandoffCurrent =
    handoffFiles &&
    handoffFiles.structure === selectedFiles.structure &&
    handoffFiles.topology === selectedFiles.topology &&
    handoffFiles.trajectory === selectedFiles.trajectory
  const currentHandoffData = isHandoffCurrent ? mdpositPublishData.data : null

  const updateSelectedFile = (role: keyof MdPositSelectedFiles, path: string) => {
    if (selectedFiles[role] === path) return
    setHandoffFiles(null)
    mdpositPublishData.reset()
    setSelectedFiles((current) => ({ ...current, [role]: path }))
  }

  const handlePrepareHandoff = () => {
    const files = { ...selectedFiles }
    setHandoffFiles(files)
    mdpositPublishData.mutate(files, {
      onSuccess: () => toast.success("MDPosit handoff files are ready."),
    })
  }

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="rounded-md border border-blue-400 bg-blue-50 p-3 text-sm text-blue-800 dark:bg-blue-950 dark:text-blue-200">
        Prepare a stateless MDPosit handoff package. This does not update the experiment publication status or wizard
        progress.
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <FileSelector
          experimentId={experiment.id}
          ext={["pdb", "gro"]}
          title="Structure"
          selectedPath={selectedFiles.structure}
          onFileSelected={(file) => updateSelectedFile("structure", file?.path ?? "")}
        />
        <FileSelector
          experimentId={experiment.id}
          ext={["top", "prmtop", "parm7", "psf"]}
          title="Topology"
          selectedPath={selectedFiles.topology}
          onFileSelected={(file) => updateSelectedFile("topology", file?.path ?? "")}
        />
        <FileSelector
          experimentId={experiment.id}
          ext={["xtc", "trr", "nc", "dcd"]}
          title="Trajectory"
          selectedPath={selectedFiles.trajectory}
          onFileSelected={(file) => updateSelectedFile("trajectory", file?.path ?? "")}
        />
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
        disabled={!canPrepareHandoff || mdpositPublishData.isPending}
        className="self-center"
      >
        {mdpositPublishData.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <CloudUpload className="mr-2 h-4 w-4" />
        )}
        Prepare MDPosit handoff
      </Button>

      {!canPrepareHandoff && (
        <p className="text-muted-foreground text-center text-xs">
          Select one structure, topology, and trajectory file before preparing the MDPosit handoff.
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
