import React, { useEffect } from "react"

import { useQueryClient } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { Atom, BarChart2, Play, SlidersHorizontal, Upload } from "lucide-react"

import { cn } from "@/lib/utils"
import { DEBUG } from "@/util/const"
import { type Experiment, type Simulation } from "@/util/types"
import { useSimulations } from "@/hooks/use-simulations"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

import AnalyzeStep from "./AnalyzeStep"
import PublishStep from "./PublishStep"
import RunStep from "./RunStep"
import WizardSetup from "./SetupStep"
import SimulationTabs, { CREATE_TAB } from "./SimulationTabs"
import TuneStep from "./TuneStep"

const STEP_ICONS = [Atom, SlidersHorizontal, Play, BarChart2, Upload]
const STEP_LABELS = ["Setup", "Tune", "Run", "Analyze", "Publish"]
const STEP_COMPONENTS = [WizardSetup, TuneStep, RunStep, AnalyzeStep, PublishStep]
const SETUP_STEP = 0
const ANALYZE_STEP = STEP_LABELS.indexOf("Analyze")
const PUBLISH_STEP = STEP_LABELS.indexOf("Publish")
const NEW_TAB = CREATE_TAB
const SIMULATIONS_POLL_MS = 5000

export interface WizardStepperProps {
  experiment: Experiment
}

export interface WizardStepProps {
  experiment: Experiment
  /** The selected simulation; null ⇔ create mode (`?tab=_new`). */
  simulation: Simulation | null
  goToStep: (step: number) => void
}

interface ResolvedWizard {
  tab: string
  step: number
  simulation: Simulation | null
  createMode: boolean
  maxStep: number
}

/** Furthest step reachable for a tab: its own ladder, plus Publish — open once published or any simulation finished MD. */
function maxAllowedStep(
  simulation: Simulation | null,
  createMode: boolean,
  experiment: Experiment,
  simulations: Simulation[]
): number {
  if (createMode) return SETUP_STEP
  const setupStep = simulation?.step ?? SETUP_STEP
  const publishReady = experiment.step >= PUBLISH_STEP || simulations.some((s) => s.step >= PUBLISH_STEP)
  return publishReady ? Math.max(setupStep, PUBLISH_STEP) : setupStep
}

/** Simulation with the most recent interaction — where the wizard lands with no tab pinned. */
function latestSimulation(simulations: Simulation[]): Simulation | null {
  return simulations.reduce<Simulation | null>(
    (latest, sim) => (latest === null || sim.last_activity > latest.last_activity ? sim : latest),
    null
  )
}

/** Resolve raw URL state to the canonical tab/step the wizard should show. */
function resolveWizard(
  search: { tab?: string; step?: number },
  simulations: Simulation[],
  experiment: Experiment
): ResolvedWizard {
  let simulation: Simulation | null = null
  let tab = search.tab

  if (search.tab === NEW_TAB) {
    tab = NEW_TAB
  } else {
    simulation = simulations.find((s) => s.name === search.tab) ?? latestSimulation(simulations)
    tab = simulation?.name ?? NEW_TAB
  }

  const createMode = tab === NEW_TAB
  const maxStep = maxAllowedStep(simulation, createMode, experiment, simulations)
  // Pinned steps are honored in bounds (button gating guards maxStep; forward
  // bumps must stick while the poll catches up).
  const step = Math.min(Math.max(search.step ?? simulation?.step ?? SETUP_STEP, SETUP_STEP), PUBLISH_STEP)

  return { tab, step, simulation, createMode, maxStep }
}

const WizardStepper = ({ experiment }: WizardStepperProps) => {
  const queryClient = useQueryClient()
  const search = useSearch({ from: "/$id/wizard" })
  const navigate = useNavigate({ from: "/$id/wizard" })
  const { data: simulations = [], isLoading: simulationsLoading } = useSimulations(experiment.id, {
    refetchInterval: SIMULATIONS_POLL_MS,
  })

  const resolved = simulationsLoading ? null : resolveWizard(search, simulations, experiment)

  const goToStep = (step: number) => navigate({ search: (prev) => ({ ...prev, step }) })

  // Keep the URL canonical (fallback tab/step replacements happen here).
  useEffect(() => {
    if (!resolved) return
    if (resolved.tab !== search.tab || resolved.step !== search.step) {
      navigate({ search: { tab: resolved.tab, step: resolved.step }, replace: true })
    }
  }, [resolved, search.tab, search.step, navigate])

  // Re-check simulation file existence on analyze; job outputs may have
  // appeared since the list was last fetched.
  useEffect(() => {
    if (resolved?.step === ANALYZE_STEP) {
      queryClient.invalidateQueries({ queryKey: ["experiment", experiment.id, "simulations"] })
    }
  }, [resolved?.step, experiment.id, queryClient])

  const selectSimulation = (name: string) => {
    const sim = simulations.find((s) => s.name === name)
    navigate({ search: { tab: name, step: sim?.step ?? SETUP_STEP } })
  }

  const createSimulation = () => navigate({ search: { tab: NEW_TAB, step: SETUP_STEP } })

  const ActiveComponent = resolved ? STEP_COMPONENTS[resolved.step] : null

  return (
    <div className="flex w-full flex-col">
      <SimulationTabs
        simulations={simulations}
        selectedName={resolved && !resolved.createMode ? resolved.tab : null}
        loading={simulationsLoading}
        onSelect={selectSimulation}
        onCreate={createSimulation}
      />

      <Card className="gap-0 rounded-t-none py-0 shadow-none">
        <div className="flex flex-col gap-5 px-6 pt-6 pb-5">
          {DEBUG && resolved && (
            <Button variant="default" onClick={() => goToStep(Math.min(resolved.step + 1, PUBLISH_STEP))}>
              DEBUG: next step
            </Button>
          )}

          <div className="flex items-center justify-center">
            {STEP_LABELS.map((label, idx) => {
              const Icon = STEP_ICONS[idx]
              const state = !resolved
                ? "locked"
                : idx === resolved.step
                  ? "active"
                  : idx < resolved.step
                    ? "done"
                    : DEBUG || idx <= resolved.maxStep
                      ? "open"
                      : "locked"

              return (
                <React.Fragment key={label}>
                  <div className="flex flex-col items-center gap-1">
                    <button
                      type="button"
                      disabled={state === "locked"}
                      onClick={() => goToStep(idx)}
                      className={cn(
                        "flex h-12 w-12 items-center justify-center rounded-full border-2 text-white transition-all",
                        state === "active" && "bg-primary border-primary scale-110 shadow-md",
                        state === "done" && "border-green-500 bg-green-500",
                        (state === "open" || state === "locked") && "bg-muted border-border text-muted-foreground",
                        state !== "locked" && state !== "active" && "cursor-pointer hover:scale-105 hover:shadow"
                      )}
                    >
                      <Icon className="h-5 w-5" />
                    </button>
                    <span
                      className={cn(
                        "text-xs font-medium",
                        state === "active" ? "text-primary" : "text-muted-foreground"
                      )}
                    >
                      {label}
                    </span>
                  </div>

                  {idx < STEP_LABELS.length - 1 && (
                    <div
                      className={cn(
                        "mx-1 mb-5 h-0.5 flex-1 transition-colors",
                        state === "done" ? "bg-green-500" : state === "active" ? "bg-primary" : "bg-border"
                      )}
                    />
                  )}
                </React.Fragment>
              )
            })}
          </div>
        </div>

        <div className="border-border border-t px-6 pt-5 pb-6">
          {resolved && ActiveComponent ? (
            <ActiveComponent experiment={experiment} simulation={resolved.simulation} goToStep={goToStep} />
          ) : null}
        </div>
      </Card>
    </div>
  )
}

export default WizardStepper
