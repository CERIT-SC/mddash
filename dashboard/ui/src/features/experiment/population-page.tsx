import { useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetExperimentQueryKey,
  getListExperimentsQueryKey,
  useCancelExperimentPopulation,
} from "@/api/generated/client"
import type { Experiment, Population } from "@/api/generated/models"
import { populationCounters, populationPolling } from "@/shared/population-state"
import { PopulationProgress } from "@/shared/ui/population-progress"
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertTitle,
  Button,
  Card,
  CardContent,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Square } from "lucide-react"
import { toast } from "sonner"

import { TitleRow } from "./title-row"

/**
 * The read-only face of a provisional experiment: measured import progress while
 * the import is in flight, and its durable safe error plus last counters after a
 * failure or cancellation. No rename/notebook/workflow controls until the
 * dataset is merged; deletion happens from the dashboard card.
 */
export function PopulationPage({ experiment, population }: { experiment: Experiment; population: Population }) {
  const queryClient = useQueryClient()
  const [cancelOpen, setCancelOpen] = useState(false)

  const cancel = useCancelExperimentPopulation({
    mutation: {
      onSuccess: () => {
        toast.success(`Import for “${experiment.name}” is being cancelled`)
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experiment.id) })
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  const active = populationPolling(population)
  const hadProgress = population.files_present > 0 || population.bytes_present > 0

  return (
    <section className="space-y-6 md:space-y-8">
      <TitleRow experiment={experiment} readOnly />

      <Card className="max-w-2xl">
        <CardContent className="space-y-4">
          {population.status === "failed" ? (
            <Alert variant="error">
              <AlertTitle>Import failed</AlertTitle>
              <AlertDescription>{population.error ?? "The repository download failed."}</AlertDescription>
            </Alert>
          ) : population.status === "cancelled" ? (
            <Alert>
              <AlertTitle>Import cancelled</AlertTitle>
              <AlertDescription>
                The repository import was cancelled before it finished. The experiment has no data yet.
              </AlertDescription>
            </Alert>
          ) : (
            <PopulationProgress population={population} />
          )}
          {!active && hadProgress && (
            <p className="text-text-muted text-sm tabular-nums">{populationCounters(population)}</p>
          )}
          {active ? (
            <Button variant="outline" onClick={() => setCancelOpen(true)} disabled={cancel.isPending}>
              <Square fill="currentColor" /> Cancel import
            </Button>
          ) : (
            <p className="text-text-muted text-sm">
              The experiment stays in your list until you delete it from My Experiments.
            </p>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel the import of “{experiment.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              The download stops immediately and the data already fetched is removed. The experiment stays in your list
              until you delete it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep importing</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => cancel.mutate({ experimentId: experiment.id })}
              disabled={cancel.isPending}
            >
              Cancel import
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
