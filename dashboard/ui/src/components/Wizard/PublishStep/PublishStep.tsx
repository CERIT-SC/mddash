import { useEffect, useMemo } from "react"

import { useQueryClient } from "@tanstack/react-query"
import { CheckCircle, CloudUpload, Folder, HardDrive, Info, Loader2, LogIn, Pencil } from "lucide-react"
import { toast } from "sonner"

import { formatFileSize } from "@/util/helpers"
import { type Experiment } from "@/util/types"
import { useFiles } from "@/hooks/use-files"
import { getMDRepoAuthUrl, useMDRepoStatus, usePublishExperiment } from "@/hooks/use-mdrepo"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const PublishStep = (props: WizardStepProps) => {
  const { experiment } = props
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
    <div className="flex justify-center p-6">
      <Card className="w-full max-w-lg">
        <CardContent className="flex flex-col items-center gap-4 pt-4">
          {/* Header */}
          <div className="flex items-center gap-2">
            <Info className="text-muted-foreground h-5 w-5" />
            <h2 className="text-lg font-semibold">Publish Experiment</h2>
          </div>

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
                  {isPublished ? "view or edit the published experiment" : "publish your experiment"}. This is a
                  one-time authorization using your e-INFRA CZ account.
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
        </CardContent>
      </Card>
    </div>
  )
}

export default PublishStep
