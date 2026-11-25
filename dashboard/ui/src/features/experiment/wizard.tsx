import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"

import { useGetExperiment, useListSimulations } from "@/api/generated/client"
import { Step, type Experiment, type Simulation } from "@/api/generated/models"
import { AnalyzeStep } from "@/features/analyze"
import { RunStep } from "@/features/run"
import { SetupStep, type SetupSource } from "@/features/setup"
import { CREATE_TAB, simulationParam, SimulationTabs } from "@/features/simulation"
import { TuneStep } from "@/features/tune"
import { populationPolling, populationReady } from "@/shared/population-state"
import { STEP_LABELS, STEPS } from "@/shared/step"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Card, CardContent, Skeleton } from "@e-infra/design-system"

import { ArchivedNotice } from "./archived-notice"
import { ConfigurationDoneNote } from "./configuration-done-note"
import { PopulationPage } from "./population-page"
import { PublishAction } from "./publish-action"
import { RenamedFilesNotice } from "./renamed-files-notice"
import { StepCard, type StepCardState } from "./step-card"
import { TitleRow } from "./title-row"

const SIMULATIONS_POLL_MS = 5000

const CARDS: Record<Step, { lockedReason?: string; foldWhenDone: boolean }> = {
  setup: { foldWhenDone: true },
  configuration: { lockedReason: "Available once the setup finishes", foldWhenDone: true },
  simulation: { lockedReason: "Starts after you choose a configuration", foldWhenDone: false },
  analysis: { lockedReason: "Available once the run saves its first frames", foldWhenDone: false },
}

const stepCardId = (step: Step) => `step-${step}`

/** Analysis lock note once a settled run left Simulation current without frames. */
const NO_FRAMES_REASON = "Re-run the simulation to produce frames"

/** Mounts with its card's content, i.e. once the card unlocks, so the scroll lands after the ladder's layout shift. */
function ScrollIntoViewOnMount({ targetId, onDone }: { targetId: string; onDone: () => void }) {
  useEffect(() => {
    document.getElementById(targetId)?.scrollIntoView?.()
    onDone()
  }, [targetId, onDone])
  return null
}

/** The ladder reports the furthest step; a live run stays current after its frames open Analysis. */
function cardStates(simulation: Simulation | undefined): Record<Step, StepCardState> {
  const reached = simulation === undefined ? 0 : STEPS.indexOf(simulation.step)
  const simulationIndex = STEPS.indexOf(Step.simulation)
  const current = simulation?.live === true && reached > simulationIndex ? simulationIndex : reached
  const state = (index: number): StepCardState =>
    index < current ? "done" : index === current ? "current" : index <= reached ? "open" : "locked"
  return Object.fromEntries(STEPS.map((step, index) => [step, state(index)])) as Record<Step, StepCardState>
}

const pollWhileAnyLive =
  (pollMs: number) =>
  (query: { state: { data: unknown } }): number | false => {
    const data = query.state.data as { status: number; data: Simulation[] } | undefined
    return data?.status === 200 && data.data.some((simulation) => simulation.live) ? pollMs : false
  }

// Poll the experiment while it is restoring from the archive or while its
// Datahugger import is in flight; the population page reads the live state.
const pollWhileExperimentActive = (query: { state: { data: unknown } }): number | false => {
  const data = query.state.data as { status: number; data: Experiment } | undefined
  if (data?.status !== 200) return false
  return data.data.archive_state === "restoring" || populationPolling(data.data.population)
    ? SIMULATIONS_POLL_MS
    : false
}

export type WizardSearch = {
  /** Selected simulation tab. simulation_path minus the ".simulation.json" suffix (may still contain slashes). */
  simulation?: string
  /** Setup source view; the default "run" never needs a param. */
  source?: SetupSource
  /** Picked tuning trial in Configuration (dropped when the job is re-tuned). */
  trial?: string
  /** Configuration view; only the non-default "manual" is worth a param. */
  mode?: "manual"
  /** Picked analysis; dropped when switching simulations. */
  analysis?: string
  /** Analysis tab; only the non-default "analysis" is worth a param. */
  tab?: "analysis"
  /** Publish dialog open. */
  publish?: true
}

type ExperimentWizardProps = {
  experimentId: string
  search: WizardSearch
  onSearchChange: (next: WizardSearch) => void
}

export function ExperimentWizard({ experimentId, search, onSearchChange }: ExperimentWizardProps) {
  const experiment = useGetExperiment(experimentId, {
    query: { retry: false, refetchInterval: pollWhileExperimentActive },
  })
  // No simulation manifest can exist before the import finishes and merges the
  // dataset, so the list query waits for the experiment's population state.
  const experimentData = experiment.data?.status === 200 ? experiment.data.data : undefined
  // The wizard heartbeat: the step ladder advances server-side, so the cards
  // must follow. Refetches scan manifests + job states, so it pauses when idle.
  const simulations = useListSimulations(experimentId, {
    query: {
      retry: false,
      enabled: experimentData === undefined ? false : populationReady(experimentData),
      refetchInterval: pollWhileAnyLive(SIMULATIONS_POLL_MS),
    },
  })

  // can_publish flips when a run finishes; this query doesn't poll. Refetch
  // once on the live→settled transition so the Publish unlock lands.
  const anyLive = simulations.data?.status === 200 && simulations.data.data.some((simulation) => simulation.live)
  const wasLive = useRef(false)
  // The simulation tab whose run just started; its Simulation card scrolls into view once it unlocks.
  const [runStartedTab, setRunStartedTab] = useState<string>()
  const clearRunStarted = useCallback(() => setRunStartedTab(undefined), [])
  const refetchExperiment = experiment.refetch
  useEffect(() => {
    if (wasLive.current && !anyLive) void refetchExperiment()
    wasLive.current = anyLive
  }, [anyLive, refetchExperiment])

  if (experiment.isError) {
    return <ApiErrorAlert error={experiment.error} onRetry={() => void experiment.refetch()} />
  }

  // The default tab comes from the experiment, so the body waits on the
  // experiment before deciding which page it is.
  const data = experimentData
  if (data === undefined) {
    return (
      <section className="space-y-6 md:space-y-8" aria-label="Loading experiment">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-16 w-full" />
      </section>
    )
  }

  // An unfinished import — and its durable terminal failures — gets the
  // read-only population page; the wizard steps need the merged dataset.
  if (data.population !== null && !populationReady(data)) {
    return <PopulationPage experiment={data} population={data.population} />
  }

  if (simulations.isError) {
    return <ApiErrorAlert error={simulations.error} onRetry={() => void simulations.refetch()} />
  }
  const list = simulations.data?.status === 200 ? simulations.data.data : undefined
  if (list === undefined) {
    return (
      <section className="space-y-6 md:space-y-8" aria-label="Loading experiment">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-16 w-full" />
      </section>
    )
  }

  // Archived experiments are frozen: the wizard's steps all need local files.
  if (data.archived_at !== null) {
    return <ArchivedNotice experiment={data} />
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
  const simTab = selected?.simulation_path ?? CREATE_TAB
  const states = cardStates(selected)

  // Publish waits for the viewed simulation to settle; other sims may still run.
  const publishReason = !(data.can_publish ?? false)
    ? "Publish unlocks once a run has finished or been stopped."
    : selected === undefined
      ? "Pick a simulation tab to publish it."
      : selected.live
        ? "Publishing unlocks once tuning and the run have finished or stopped on this simulation."
        : undefined

  // Wizard params ride along on every navigation so remounts keep user context.
  const updateSearch = (next: WizardSearch) =>
    onSearchChange({
      source: search.source,
      trial: search.trial,
      mode: search.mode,
      analysis: search.analysis,
      tab: search.tab,
      ...next,
      simulation:
        next.simulation === undefined || next.simulation === CREATE_TAB
          ? next.simulation
          : simulationParam(next.simulation),
    })

  const stepContent = (step: Step): ReactNode => {
    if (step === Step.setup) {
      return (
        <SetupStep
          experimentId={experimentId}
          experiment={data}
          simulation={selected}
          creating={creating}
          hasSimulations={list.length > 0}
          source={search.source ?? "run"}
          onSourceChange={(source) =>
            updateSearch({ simulation: simTab, source: source === "run" ? undefined : source })
          }
          onOpenSimulation={(simulation) => updateSearch({ simulation })}
        />
      )
    }
    // Later cards stay locked on the create tab, so they never render without a simulation.
    if (selected === undefined) return null
    switch (step) {
      case Step.configuration:
        return (
          <TuneStep
            experimentId={experimentId}
            engine={data.engine}
            simulation={selected}
            trialId={search.trial}
            mode={search.mode ?? "tuning"}
            onTrialIdChange={(trial) => updateSearch({ simulation: simTab, trial })}
            onModeChange={(mode) =>
              updateSearch({ simulation: simTab, mode: mode === "manual" ? "manual" : undefined })
            }
            onRunStarted={() => setRunStartedTab(simTab)}
          />
        )
      case Step.simulation:
        return (
          <>
            {runStartedTab === simTab && (
              <ScrollIntoViewOnMount targetId={stepCardId(Step.simulation)} onDone={clearRunStarted} />
            )}
            <RunStep experimentId={experimentId} engine={data.engine} simulation={selected} />
          </>
        )
      case Step.analysis:
        return (
          <AnalyzeStep
            experimentId={experimentId}
            engine={data.engine}
            simulation={selected}
            selectedAnalysis={search.analysis}
            onSelectedAnalysisChange={(analysis) => updateSearch({ simulation: simTab, analysis })}
            tab={search.tab ?? "trajectory"}
            onTabChange={(next) =>
              updateSearch({ simulation: simTab, tab: next === "analysis" ? "analysis" : undefined })
            }
          />
        )
    }
  }

  const lockedNote = (step: Step): string | undefined =>
    step === Step.analysis && states.simulation === "current" && selected?.live !== true
      ? NO_FRAMES_REASON
      : CARDS[step].lockedReason

  const doneNote = (step: Step): ReactNode => {
    if (step === Step.setup && selected !== undefined) return `“${selected.name}” is ready`
    if (step === Step.configuration && selected !== undefined)
      return <ConfigurationDoneNote experimentId={experimentId} engine={data.engine} simulation={selected} />
    return undefined
  }

  const renamedPaths = data.population?.renamed_paths ?? []

  return (
    <section className="space-y-6 md:space-y-8">
      <TitleRow
        experiment={data}
        action={
          <PublishAction
            experiment={data}
            simulation={selected}
            reason={publishReason}
            open={search.publish === true}
            onOpenChange={(open) => updateSearch({ simulation: simTab, publish: open ? true : undefined })}
            // Re-asserting the typed search drops the MDRepo OAuth params and keeps the dialog open.
            onOAuthHandled={() => updateSearch({ simulation: simTab, publish: true })}
          />
        }
      />
      {renamedPaths.length > 0 && <RenamedFilesNotice paths={renamedPaths} />}

      <div>
        <SimulationTabs
          experimentId={experimentId}
          simulations={list}
          value={simTab}
          onValueChange={(simulation) => updateSearch({ simulation, analysis: undefined })}
          onDeleted={(deleted) => {
            // The URL still points at the deleted manifest; {} resets to the default tab.
            if (
              search.simulation !== undefined &&
              simulationParam(search.simulation) === simulationParam(deleted.simulation_path)
            )
              onSearchChange({})
          }}
        />

        {/* bg-background like DS dialogs: TabsList, Input and TableRow paint
            bg-surface and only stay visible on the canvas color; restyle with
            the tab boxes. */}
        {/* box-shadow over drop-shadow: filter would confine molstar's expanded (fixed) viewport to this card. */}
        <Card className="border-border bg-background rounded-t-none border py-0 shadow-[0_4px_4px_rgba(0,0,0,0.15)] drop-shadow-none hover:drop-shadow-none">
          <CardContent className="pt-6 pb-6">
            {/* Keyed by tab: fold state and step-local state belong to one simulation. */}
            <ol key={simTab} role="list" aria-label="Steps" className="space-y-4">
              {STEPS.map((step, index) => (
                <StepCard
                  key={step}
                  id={stepCardId(step)}
                  position={index + 1}
                  title={STEP_LABELS[step]}
                  state={states[step]}
                  note={
                    states[step] === "locked" ? lockedNote(step) : states[step] === "done" ? doneNote(step) : undefined
                  }
                  foldWhenDone={CARDS[step].foldWhenDone}
                >
                  {stepContent(step)}
                </StepCard>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
