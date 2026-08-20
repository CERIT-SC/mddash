import { useGetExperiment, useListSimulations } from "@/api/generated/client"
import { SetupStep, type SetupSource } from "@/features/setup"
import { CREATE_TAB, SimulationTabs } from "@/features/simulation"
import { TuneStep } from "@/features/tune"
import { ladderStepIndex } from "@/shared/steps"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Stepper, StepperContent, StepperHeader } from "@/shared/ui/stepper"
import { Card, CardContent, Skeleton } from "@e-infra/design-system"
import { Atom, ChartColumn, Play, SlidersHorizontal, Upload } from "lucide-react"

import { TitleRow } from "./title-row"

const STEPS = [
  { label: "Setup", icon: Atom },
  { label: "Tune", icon: SlidersHorizontal },
  { label: "Run", icon: Play },
  { label: "Analyze", icon: ChartColumn },
  { label: "Publish", icon: Upload },
]

const LAST_STEP = STEPS.length - 1

export type WizardSearch = {
  /** Selected simulation tab — the simulation_path, which may contain slashes. */
  simulation?: string
  /** Current wizard step (0-based); defaults to the simulation's own progress. */
  step?: number
  /** Setup source view; only the non-default "manual" is worth a param. */
  source?: SetupSource
  /** Picked tuning trial on the Tune step (dropped when the job is re-tuned). */
  trial?: string
  /** Tune step view; only the non-default "manual" is worth a param. */
  mode?: "manual"
}

type ExperimentWizardProps = {
  experimentId: string
  search: WizardSearch
  onSearchChange: (next: WizardSearch) => void
}

const clampStep = (step: number) => Math.max(0, Math.min(step, LAST_STEP))

export function ExperimentWizard({ experimentId, search, onSearchChange }: ExperimentWizardProps) {
  const experiment = useGetExperiment(experimentId, { query: { retry: false } })
  const simulations = useListSimulations(experimentId, { query: { retry: false } })

  if (experiment.isError) {
    return <ApiErrorAlert error={experiment.error} onRetry={() => void experiment.refetch()} />
  }
  if (simulations.isError) {
    return <ApiErrorAlert error={simulations.error} onRetry={() => void simulations.refetch()} />
  }

  // The title and the default tab both come from the experiment, so the whole
  // body waits on both queries rather than re-resolving the tab mid-paint.
  const data = experiment.data?.status === 200 ? experiment.data.data : undefined
  const list = simulations.data?.status === 200 ? simulations.data.data : undefined
  if (data === undefined || list === undefined) {
    return (
      <section className="space-y-6 md:space-y-8" aria-label="Loading experiment">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-16 w-full" />
      </section>
    )
  }

  // The unnamed create tab doubles as the empty state when there are no manifests to select.
  const creating = search.simulation === CREATE_TAB || list.length === 0
  const selected = creating
    ? undefined
    : (list.find((candidate) => candidate.simulation_path === search.simulation) ??
      (data.latest_simulation_path !== null
        ? list.find((candidate) => candidate.simulation_path === data.latest_simulation_path)
        : undefined) ??
      list[0])
  // The API ladder decodes through the shared mapping; the URL-owned step is used verbatim.
  // A simulation that does not exist yet has no progress of its own, so create
  // mode always lands on Setup.
  const maxStep = selected === undefined ? 0 : ladderStepIndex(selected.step)
  const step = selected === undefined ? 0 : clampStep(search.step ?? maxStep)
  const tab = selected?.simulation_path ?? CREATE_TAB

  // Setup/Tune URL params ride along on every navigation so remounts keep user
  // context; only a full reset drops them.
  const updateSearch = (next: WizardSearch) =>
    onSearchChange({ source: search.source, trial: search.trial, mode: search.mode, ...next })

  return (
    <section className="space-y-6 md:space-y-8">
      <TitleRow experiment={data} />

      <div>
        <SimulationTabs
          experimentId={experimentId}
          simulations={list}
          value={tab}
          onValueChange={(simulation) => updateSearch({ simulation })}
          onDeleted={(deleted) => {
            // The URL still points at the deleted manifest; drop the selection so
            // the refreshed list falls back to its default tab.
            if (search.simulation === deleted.simulation_path) onSearchChange({})
          }}
        />

        {/* Shares its top edge with the tab boxes — restyle them together. */}
        <Card className="border-border rounded-t-none border bg-white">
          <CardContent className="pt-6 md:pt-8 lg:pt-12">
            <Stepper
              step={step}
              totalSteps={STEPS.length}
              onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
            >
              {/* mb-0 drops the header's reserved bottom margin. */}
              <StepperHeader steps={STEPS} className="mb-0" maxStep={maxStep} />
              <StepperContent>
                <SetupStep
                  experimentId={experimentId}
                  experiment={data}
                  simulation={selected}
                  creating={creating}
                  source={search.source ?? "notebook"}
                  onSourceChange={(source) => updateSearch({ simulation: tab, step: search.step, source })}
                  onOpenSimulation={(simulation) => updateSearch({ simulation })}
                />
                {/* Create mode pins the stepper to Setup, so this placeholder never renders. */}
                {selected === undefined ? (
                  <div />
                ) : (
                  <TuneStep
                    experimentId={experimentId}
                    engine={data.engine}
                    simulation={selected}
                    trialId={search.trial}
                    mode={search.mode ?? "tuning"}
                    onTrialIdChange={(trial) => updateSearch({ simulation: tab, step: search.step, trial })}
                    onModeChange={(mode) =>
                      updateSearch({
                        simulation: tab,
                        step: search.step,
                        mode: mode === "manual" ? "manual" : undefined,
                      })
                    }
                    onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
                  />
                )}
                {STEPS.slice(2).map(({ label }) => (
                  <div key={label} />
                ))}
              </StepperContent>
            </Stepper>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
