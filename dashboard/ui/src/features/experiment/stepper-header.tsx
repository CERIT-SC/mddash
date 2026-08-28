import type { Engine, Simulation } from "@/api/generated/models"
import { jobProgressPercent, useSimulationJobQuery } from "@/features/run"
import { StepperHeader, type Step } from "@/shared/ui/stepper"

const RUN_STEP = 2

type WizardStepperHeaderProps = {
  experimentId: string
  engine: Engine
  /** Undefined in create mode — no job to poll. */
  simulation: Simulation | undefined
  steps: Step[]
  maxStep: number
  unlockedIndexes: readonly number[]
  pollMs: number
}

export function WizardStepperHeader({
  experimentId,
  engine,
  simulation,
  steps,
  maxStep,
  unlockedIndexes,
  pollMs,
}: WizardStepperHeaderProps) {
  const { job } = useSimulationJobQuery(experimentId, simulation?.simulation_path ?? "", engine, pollMs, {
    enabled: simulation !== undefined,
  })
  const progress = job !== undefined && job.is_live ? jobProgressPercent(job) : null
  const stepsWithProgress = steps.map((step, index) => (index === RUN_STEP ? { ...step, progress } : step))
  return (
    <StepperHeader steps={stepsWithProgress} className="mb-0" maxStep={maxStep} unlockedIndexes={unlockedIndexes} />
  )
}
