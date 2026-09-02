import { useGetExperiment, useListSimulations } from "@/api/generated/client"
import type { Simulation } from "@/api/generated/models"
import { AnalyzeStep } from "@/features/analyze"
import { PublishStep } from "@/features/publish"
import { RunStep } from "@/features/run"
import { SetupStep, type SetupSource } from "@/features/setup"
import { CREATE_TAB, simulationParam, SimulationTabs } from "@/features/simulation"
import { TuneStep } from "@/features/tune"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Stepper, StepperContent } from "@/shared/ui/stepper"
import { Card, CardContent, Separator, Skeleton } from "@e-infra/design-system"
import { Atom, ChartColumn, Play, SlidersHorizontal, Upload } from "lucide-react"

import { WizardStepperHeader } from "./stepper-header"
import { TitleRow } from "./title-row"

const STEPS = [
  { label: "Setup", icon: Atom },
  { label: "Tune", icon: SlidersHorizontal },
  { label: "Run", icon: Play },
  { label: "Analyze", icon: ChartColumn },
  { label: "Publish", icon: Upload },
]

const LAST_STEP = STEPS.length - 1

const SIMULATIONS_POLL_MS = 5000

const pollWhileAnyLive =
  (pollMs: number) =>
  (query: { state: { data: unknown } }): number | false => {
    const data = query.state.data as { status: number; data: Simulation[] } | undefined
    return data?.status === 200 && data.data.some((simulation) => simulation.live) ? pollMs : false
  }

export type WizardSearch = {
  /** Selected simulation tab — simulation_path minus the ".simulation.json" suffix (may still contain slashes). */
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

export function ExperimentWizard({ experimentId, search, onSearchChange }: ExperimentWizardProps) {
  const experiment = useGetExperiment(experimentId, { query: { retry: false } })
  // The poll is the wizard heartbeat — the step ladder advances server-side when
  // a run finishes and the stepper must follow. Each refetch scans manifests +
  // job states, so it pauses once no simulation has work in flight.
  const simulations = useListSimulations(experimentId, {
    query: { retry: false, refetchInterval: pollWhileAnyLive(SIMULATIONS_POLL_MS) },
  })

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
  // Idempotent strip keeps legacy suffixed links resolving.
  const requested = search.simulation === undefined ? undefined : simulationParam(search.simulation)
  const selected = creating
    ? undefined
    : (list.find((candidate) => simulationParam(candidate.simulation_path) === requested) ??
      (data.latest_simulation_path !== null
        ? list.find((candidate) => candidate.simulation_path === data.latest_simulation_path)
        : undefined) ??
      list[0])
  // The API owns phase semantics: step is already the stepper index (Setup 0,
  // Tune 1, Run 2, Analyze 3), consumed directly with no decode. can_publish
  // unlocks ONLY the experiment-level Publish marker. Create mode: Setup.
  const ownStep = selected === undefined ? 0 : selected.step
  const maxStep = selected === undefined ? 0 : ownStep
  // Content gates like the header: a URL step past the unlocks (stale Publish
  // bookmark) falls back to the simulation's own progress, never locked UI.
  const requestedStep = search.step ?? ownStep
  const unlocked = requestedStep <= maxStep || ((data.can_publish ?? false) && requestedStep === LAST_STEP)
  const step = selected === undefined ? 0 : unlocked ? requestedStep : ownStep
  const tab = selected?.simulation_path ?? CREATE_TAB

  // Setup/Tune URL params ride along on every navigation so remounts keep user
  // context; only a full reset drops them.
  const updateSearch = (next: WizardSearch) =>
    onSearchChange({
      source: search.source,
      trial: search.trial,
      mode: search.mode,
      ...next,
      simulation:
        next.simulation === undefined || next.simulation === CREATE_TAB
          ? next.simulation
          : simulationParam(next.simulation),
    })

  // The five steps are StepperContent's direct children in index order (Setup=0
  // .. Publish=4). Create mode keeps only Setup; the rest render once a
  // simulation exists.
  const steps = [
    <SetupStep
      key="setup"
      experimentId={experimentId}
      experiment={data}
      simulation={selected}
      creating={creating}
      source={search.source ?? "notebook"}
      onSourceChange={(source) => updateSearch({ simulation: tab, step: search.step, source })}
      onOpenSimulation={(simulation) => updateSearch({ simulation })}
      onContinue={() => updateSearch({ simulation: tab, step: 1 })}
    />,
    ...(selected === undefined
      ? []
      : [
          <TuneStep
            key="tune"
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
          />,
          <RunStep
            key="run"
            experimentId={experimentId}
            engine={data.engine}
            simulation={selected}
            onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
          />,
          <AnalyzeStep
            key="analyze"
            experimentId={experimentId}
            engine={data.engine}
            simulation={selected}
            canPublish={data.can_publish ?? false}
            onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
          />,
          <PublishStep
            key="publish"
            experiment={data}
            simulation={selected}
            onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
            // Re-asserting the typed search drops the MDRepo OAuth params from the URL.
            onOAuthHandled={() => updateSearch({ simulation: tab, step })}
          />,
        ]),
  ]

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
            if (
              search.simulation !== undefined &&
              simulationParam(search.simulation) === simulationParam(deleted.simulation_path)
            )
              onSearchChange({})
          }}
        />

        {/* Shares its top edge with the tab boxes — restyle them together. The
            panel stays on bg-background (like DS dialogs): TabsList, Input and
            TableRow all paint bg-surface and only stay visible on the canvas
            color; on a bg-surface card they blend into the card face. */}
        {/* box-shadow over drop-shadow: filter would confine molstar's expanded (fixed) viewport to this card. */}
        <Card className="border-border bg-background rounded-t-none border shadow-[0_4px_4px_rgba(0,0,0,0.15)] drop-shadow-none hover:drop-shadow-none">
          <CardContent className="pt-6 md:pt-8 lg:pt-12">
            <Stepper
              step={step}
              totalSteps={STEPS.length}
              onStepChange={(next) => updateSearch({ simulation: tab, step: next })}
            >
              <WizardStepperHeader
                experimentId={experimentId}
                engine={data.engine}
                simulation={selected}
                steps={STEPS}
                maxStep={maxStep}
                unlockedIndexes={data.can_publish ? [LAST_STEP] : []}
                pollMs={SIMULATIONS_POLL_MS}
              />
              <Separator className="mt-4" />
              <StepperContent>{steps}</StepperContent>
            </Stepper>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
