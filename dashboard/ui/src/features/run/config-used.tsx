import { useMemo } from "react"

import { Engine, JobStatus, type AmberJob, type GromacsJob, type SimulationJob } from "@/api/generated/models"
import { selectable, suggest, TrialRowCells, TrialsTableHeader, type TrialRow } from "@/features/tune"
import { Table, TableBody, TableRow } from "@e-infra/design-system"
import { Settings } from "lucide-react"

/** A trial matches the run when the submitted job's hardware config equals the trial's. */
function matchesJobConfig(engine: Engine, row: TrialRow, job: SimulationJob): boolean {
  if (row.np !== job.np || row.ntomp !== job.ntomp) return false
  if (engine === Engine.AMBER) {
    const amber = job as AmberJob
    return row.binary === (amber.binary ?? null) && row.ewald === (amber.ewald ?? null)
  }
  const gmx = job as GromacsJob
  return row.pme === (gmx.pme ?? null) && row.nb === (gmx.nb ?? null)
}

/** Fallback row from the job itself when no tuner trial matches (manual/custom config). */
function jobConfigRow(engine: Engine, job: SimulationJob): TrialRow {
  const gmx = job as GromacsJob
  const amber = job as AmberJob
  return {
    id: "__run-config__",
    status: JobStatus.FINISHED,
    performance: null,
    estTimeHours: null,
    estCost: null,
    np: job.np,
    ntomp: job.ntomp,
    pme: engine !== Engine.AMBER ? (gmx.pme ?? null) : null,
    nb: engine !== Engine.AMBER ? (gmx.nb ?? null) : null,
    binary: engine === Engine.AMBER ? (amber.binary ?? null) : null,
    ewald: engine === Engine.AMBER ? (amber.ewald ?? null) : null,
  }
}

type ConfigUsedProps = {
  engine: Engine
  job: SimulationJob
  trials: TrialRow[]
}

/**
 * The configuration the run was submitted with: the tuner trial it matches
 * (estimates and suggestions included), or the job's bare config otherwise.
 */
export function ConfigUsed({ engine, job, trials }: ConfigUsedProps) {
  // Prefer a finished match: a still-running/errored rerun of the same config
  // must not shadow the tuned estimates and suggestions.
  const matched = useMemo(
    () =>
      trials.find((row) => selectable(row) && matchesJobConfig(engine, row, job)) ??
      trials.find((row) => matchesJobConfig(engine, row, job)),
    [engine, trials, job]
  )
  const row = matched ?? jobConfigRow(engine, job)
  const { fastestId, ecoId } = suggest(trials)

  return (
    <section aria-label="Configuration used" className="space-y-3">
      <p className="text-text-muted flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
        <Settings className="h-3.5 w-3.5" aria-hidden />
        Configuration used
      </p>
      <div className="overflow-x-auto">
        <Table>
          <TrialsTableHeader engine={engine} pickColumn={false} />
          <TableBody>
            <TableRow>
              <TrialRowCells engine={engine} row={row} fastest={row.id === fastestId} eco={row.id === ecoId} />
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </section>
  )
}
