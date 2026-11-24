import type { Experiment, Population } from "@/api/generated/models"
import { formatBytes } from "@/shared/format"

/**
 * The experiment is ready for the ordinary workflows: it has no Datahugger import,
 * or its import finished and the dataset is merged. Failed/cancelled imports are
 * durable terminal states that keep the experiment read-only until deletion.
 */
export function populationReady(experiment: Pick<Experiment, "population">): boolean {
  return experiment.population === null || experiment.population.status === "succeeded"
}

/** The import is still in flight; the UI polls the experiment while in these states. */
export function populationPolling(population: Population | null | undefined): boolean {
  return population?.status === "queued" || population?.status === "running" || population?.status === "cancelling"
}

/** TanStack Query refetchInterval: poll an Experiment detail only while its import is in flight. */
export function pollWhilePopulationActive(pollMs: number) {
  return (query: { state: { data: unknown } }): number | false => {
    const data = query.state.data as { status: number; data: Pick<Experiment, "population"> } | undefined
    return data?.status === 200 && populationPolling(data.data.population) ? pollMs : false
  }
}

/** "N of M files present · X of Y" — the counters never claim completed or validated files. */
export function populationCounters(population: Population): string {
  const filesText =
    population.files_total !== null && population.files_total !== undefined
      ? `${population.files_present} of ${population.files_total} files present`
      : `${population.files_present} ${population.files_present === 1 ? "file" : "files"} present`
  const bytesText =
    population.bytes_total !== null && population.bytes_total !== undefined
      ? `${formatBytes(population.bytes_present)} of ${formatBytes(population.bytes_total)}`
      : formatBytes(population.bytes_present)
  return `${filesText} · ${bytesText}`
}
