import type { Engine, Simulation } from "@/api/generated/models"
import { jobConfigRequest, useSimulationJobQuery } from "@/features/run"
import { configSummary, toHardwareValues } from "@/features/tune"

const RUN_POLL_MS = 5000

/** The folded Configuration card's line: the configuration the run was submitted with. */
export function ConfigurationDoneNote({
  experimentId,
  engine,
  simulation,
}: {
  experimentId: string
  engine: Engine
  simulation: Simulation
}) {
  const { job } = useSimulationJobQuery(experimentId, simulation.simulation_path, engine, RUN_POLL_MS)
  return job === undefined
    ? "Run configuration chosen"
    : configSummary(engine, toHardwareValues(jobConfigRequest(engine, job)))
}
