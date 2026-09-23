import type { Engine, Simulation } from "@/api/generated/models"
import { jobProgressPercent, useSimulationJobQuery } from "@/features/run"
import { StepperHeader, type Step } from "@/shared/ui/stepper"

const RUN_STEP = 2
const PUBLISH_STEP = 4

type WizardStepperHeaderProps = {
  experimentId: string
  engine: Engine
  simulation: Simulation | undefined
  steps: Step[]
  maxStep: number
  unlockedIndexes: readonly number[]
  /** Tooltip on the locked Publish marker; undefined once Publish is reachable. */
  publishReason: string | undefined
  pollMs: number
}

export function WizardStepperHeader({
  experimentId,
  engine,
  simulation,
  steps,
  maxStep,
  unlockedIndexes,
  publishReason,
  pollMs,
}: WizardStepperHeaderProps) {
  const { job } = useSimulationJobQuery(experimentId, simulation?.simulation_path ?? "", engine, pollMs, {
    enabled: simulation !== undefined,
  })
  const progress = job !== undefined && job.is_live ? jobProgressPercent(job) : null
  const stepsWithProgress = steps.map((step, index) => {
    if (index === RUN_STEP) return { ...step, progress }
    if (index === PUBLISH_STEP) return { ...step, lockedTitle: publishReason }
    return step
  })
  return (
    <StepperHeader steps={stepsWithProgress} className="mb-0" maxStep={maxStep} unlockedIndexes={unlockedIndexes} />
  )
}
