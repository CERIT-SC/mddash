import { toApiError } from "@/api/errors"
import { getGetExperimentQueryKey, getListExperimentsQueryKey, useRestoreExperiment } from "@/api/generated/client"
import type { Experiment } from "@/api/generated/models"
import { formatBytes, relativeTime } from "@/shared/format"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Alert, AlertDescription, AlertTitle, Button, H1, P } from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Archive, LoaderCircle } from "lucide-react"
import { toast } from "sonner"

export function ArchivedNotice({ experiment }: { experiment: Experiment }) {
  const queryClient = useQueryClient()
  const restore = useRestoreExperiment({
    mutation: {
      onSuccess: () => {
        toast.success(`Restoring “${experiment.name}” (this can take a while)`)
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experiment.id) })
      },
    },
  })

  // Durable states, not mutation-only: a deep link can land mid-restore or after a failure.
  const restoring = experiment.archive_state === "restoring" || restore.isPending
  const restoreFailed = experiment.archive_state === "restore_failed"

  return (
    <section className="mx-auto flex max-w-lg flex-col items-center gap-6 pt-12 text-center">
      <Archive className="text-text-muted h-10 w-10" aria-hidden="true" />
      <div className="space-y-2">
        <H1>This experiment is archived</H1>
        <P className="text-text-muted">
          “{experiment.name}” was archived {relativeTime(experiment.archived_at ?? experiment.updated_at)}
          {experiment.size_bytes !== null &&
            experiment.size_bytes !== undefined &&
            ` · ${formatBytes(experiment.size_bytes)}`}
          . Its data lives only in S3 storage; restore it to keep working with it.
        </P>
      </div>
      {restoreFailed && (
        <Alert variant="error" className="text-left">
          <AlertTitle>Restoring failed</AlertTitle>
          <AlertDescription>The archived copy is intact; you can retry restoring.</AlertDescription>
        </Alert>
      )}
      {restoring ? (
        <Button disabled>
          <LoaderCircle className="animate-spin" aria-hidden="true" /> Restoring…
        </Button>
      ) : restore.isError ? (
        <ApiErrorAlert
          error={toApiError(restore.error)}
          onRetry={() => restore.mutate({ experimentId: experiment.id })}
        />
      ) : (
        <Button onClick={() => restore.mutate({ experimentId: experiment.id })}>Restore</Button>
      )}
    </section>
  )
}
