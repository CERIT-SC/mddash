import { useGetExperiment, useListSimulations } from "@/api/generated/client"
import { SetupStep, type SetupSource } from "@/features/setup"
import { CREATE_TAB, SimulationTabs } from "@/features/simulation"
import { ladderStepIndex } from "@/shared/steps"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Card, CardContent, Skeleton, Stepper, StepperContent, StepperHeader } from "@e-infra/design-system"

import { TitleRow } from "./title-row"

const STEPS = [{ label: "Setup" }, { label: "Tune" }, { label: "Run" }, { label: "Analyze" }, { label: "Publish" }]

const LAST_STEP = STEPS.length - 1

export type WizardSearch = {
  /** Selected simulation tab — the simulation_path, which may contain slashes. */
  simulation?: string
  /** Current wizard step (0-based); defaults to the simulation's own progress. */
  step?: number
  /** Setup source view; only the non-default "manual" is worth a param. */
  source?: SetupSource
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
  const step = selected === undefined ? 0 : clampStep(search.step ?? ladderStepIndex(selected.step))
  const tab = selected?.simulation_path ?? CREATE_TAB

  // The Setup source view rides along on every navigation (remounts must not
  // bounce a mid-form user back to the default); only a full reset drops it.
  const updateSearch = (next: WizardSearch) => onSearchChange({ source: search.source, ...next })

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
            {/* URL owns the step; initialStep re-syncs the uncontrolled DS Stepper.
                TODO(CERIT-SC/design-system#110): switch to controlled `step` — until
                then it can drift from the URL in create mode, where the Setup pin is display-only. */}
            <Stepper
              initialStep={step}
              totalSteps={STEPS.length}
              onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
            >
              {/* Mock-mandated: mb-0 (DS reserves it for content below) + max-w-none
                  on the header's capped bar. Brittle if DS renames that utility. */}
              <StepperHeader steps={STEPS} className="mb-0 [&_.max-w-lg]:max-w-none" />
              {/* No StepperFooter — the DS header already renders Previous/Next. */}
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
                {STEPS.slice(1).map(({ label }) => (
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
