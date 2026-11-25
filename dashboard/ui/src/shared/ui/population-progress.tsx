import type { Population, PopulationPhase } from "@/api/generated/models"
import { populationCounters } from "@/shared/population-state"
import { Alert, AlertDescription, AlertTitle, Progress } from "@e-infra/design-system"
import { LoaderCircle } from "lucide-react"

const PHASE_LABELS: Record<PopulationPhase, string> = {
  starting: "Preparing the import",
  crawling: "Scanning the repository",
  downloading: "Downloading the repository",
  finalizing: "Finishing the import",
  cancelling: "Cancelling the import",
}

/**
 * Measured import progress. The counters are "files present", never completed or
 * validated files; a determinate percentage is shown only when every selected file
 * has a known size, otherwise the bar stays indeterminate.
 */
export function PopulationProgress({ population }: { population: Population }) {
  const percent =
    population.byte_percentage !== null && population.byte_percentage !== undefined
      ? Math.max(0, Math.min(100, population.byte_percentage))
      : null

  return (
    <div className="space-y-2" aria-live="polite">
      {population.status === "cancelling" && population.error && (
        <Alert variant="error">
          <AlertTitle>Cancellation not finished</AlertTitle>
          <AlertDescription>{population.error}</AlertDescription>
        </Alert>
      )}
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="flex items-center gap-2">
          <LoaderCircle className="text-text-muted h-4 w-4 animate-spin" aria-hidden="true" />
          {PHASE_LABELS[population.phase]}…
        </span>
        {percent !== null && <span className="tabular-nums">{Math.round(percent)}%</span>}
      </div>
      {percent === null ? (
        <div className="bg-surface-raised h-1.5 w-full rounded-full" aria-hidden="true" />
      ) : (
        // DS ≤ 0.1.9 Progress destructures `value` away from the Radix Root, so the
        // determinate state never reaches AT. Set aria-valuenow explicitly.
        <Progress value={percent} aria-valuenow={percent} aria-label="Repository import progress" />
      )}
      <p className="text-text-muted text-sm tabular-nums">{populationCounters(population)}</p>
    </div>
  )
}
