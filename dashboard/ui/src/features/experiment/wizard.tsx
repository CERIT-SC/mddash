import { useState } from "react"

import { toApiError } from "@/api/errors"
import {
  getGetExperimentQueryKey,
  getListExperimentsQueryKey,
  useGetExperiment,
  useListSimulations,
  useUpdateExperiment,
} from "@/api/generated/client"
import type { Experiment } from "@/api/generated/models"
import { formatDate } from "@/shared/format"
import { sourceLabel } from "@/shared/source"
import { ladderStepIndex } from "@/shared/steps"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  H1,
  Input,
  Label,
  Skeleton,
  Stepper,
  StepperContent,
  StepperHeader,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Calendar, GitBranch, Pencil } from "lucide-react"
import { toast } from "sonner"

import { CREATE_TAB, SimulationTabs } from "./simulation-tabs"
import { SourceItem } from "./source-metadata"

const STEPS = [{ label: "Setup" }, { label: "Tune" }, { label: "Run" }, { label: "Analyze" }, { label: "Publish" }]

const LAST_STEP = STEPS.length - 1

export type WizardSearch = {
  /** Selected simulation tab — the simulation_path, which may contain slashes. */
  simulation?: string
  /** Current wizard step (0-based); defaults to the simulation's own progress. */
  step?: number
}

type ExperimentWizardProps = {
  experimentId: string
  search: WizardSearch
  onSearchChange: (next: WizardSearch) => void
}

const clampStep = (step: number) => Math.max(0, Math.min(step, LAST_STEP))

/** "sb-ncbr/mddash-notebooks.git" from a full git URL (https or git@). */
function shortRepo(repo: string): string {
  const ssh = /^git@[^:]+:(.+)$/.exec(repo)
  if (ssh) return ssh[1]
  try {
    return new URL(repo).pathname.replace(/^\//, "")
  } catch {
    return repo
  }
}

function TitleRow({ experiment }: { experiment: Experiment }) {
  const queryClient = useQueryClient()
  const [renameOpen, setRenameOpen] = useState(false)
  const [nextName, setNextName] = useState(experiment.name)

  const rename = useUpdateExperiment({
    mutation: {
      onSuccess: () => {
        toast.success("Experiment renamed")
        setRenameOpen(false)
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experiment.id) })
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  function openRename() {
    setNextName(experiment.name)
    setRenameOpen(true)
  }

  function submitRename(event: React.FormEvent) {
    event.preventDefault()
    const name = nextName.trim()
    if (!name || name === experiment.name) return
    rename.mutate({ experimentId: experiment.id, data: { name } })
  }

  const items: React.ReactNode[] = [
    sourceLabel(experiment.source) ? <SourceItem key="source" experiment={experiment} /> : null,
    <span key="created" className="flex items-center gap-1.5">
      <Calendar size={14} aria-hidden className="shrink-0" />
      {formatDate(experiment.created_at)}
    </span>,
    experiment.notebooks_repo ? (
      <a
        key="repo"
        href={experiment.notebooks_repo}
        target="_blank"
        rel="noopener noreferrer"
        className="flex max-w-52 items-center gap-1.5 hover:underline"
        title={experiment.notebooks_repo}
      >
        <GitBranch size={14} aria-hidden className="shrink-0" />
        <span className="truncate">{shortRepo(experiment.notebooks_repo)}</span>
      </a>
    ) : null,
  ].filter((item) => item !== null)

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <H1>Experiment</H1>
      <Button
        variant="outline"
        size="sm"
        onClick={openRename}
        aria-label="Rename experiment"
        className="max-w-full min-w-0"
      >
        <span className="truncate">{experiment.name}</span>
        <Pencil aria-hidden="true" className="shrink-0" />
      </Button>
      {items.length > 0 && <span className="bg-border h-8 w-px" aria-hidden="true" />}
      <div className="text-text-muted flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {items.map((item, index) => (
          <span key={index} className="flex items-center gap-2">
            {index > 0 && <span aria-hidden="true">·</span>}
            {item}
          </span>
        ))}
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename experiment</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitRename} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`rename-${experiment.id}`}>Name</Label>
              <Input
                id={`rename-${experiment.id}`}
                value={nextName}
                onChange={(event) => setNextName(event.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={rename.isPending || !nextName.trim()}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

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

  return (
    <section className="space-y-6 md:space-y-8">
      <TitleRow experiment={data} />

      <div>
        <SimulationTabs
          experimentId={experimentId}
          simulations={list}
          value={tab}
          onValueChange={(simulation) => onSearchChange({ simulation })}
          onDeleted={(deleted) => {
            // The URL still points at the deleted manifest; drop the selection so
            // the refreshed list falls back to its default tab.
            if (search.simulation === deleted.simulation_path) onSearchChange({})
          }}
        />

        {/* Shares its top edge with the tab boxes — restyle them together. */}
        <Card className="border-border rounded-t-none border bg-white">
          <CardContent className="pt-6 md:pt-8 lg:pt-12">
            {/* URL owns the step: onStepChange only fires on user navigation, while a
                changed initialStep re-syncs the DS Stepper's internal state.
                TODO(CERIT-SC/design-system#110): switch to the controlled `step` prop
                once released — the uncontrolled Stepper can drift from the URL-owned
                step in create mode, where the Setup pin is display-only. */}
            <Stepper
              initialStep={step}
              totalSteps={STEPS.length}
              onStepChange={(next) => onSearchChange({ simulation: tab, step: next })}
            >
              {/* Two fixed overrides, both mock-mandated: mb-0 (DS stacks an mb-8 meant
                  for content below) and max-w-none on the header's capped max-w-lg bar
                  so the stepper spans the panel. Brittle if DS renames that utility. */}
              <StepperHeader steps={STEPS} className="mb-0 [&_.max-w-lg]:max-w-none" />
              {/* No StepperFooter — the DS header already renders Previous/Next. */}
              <StepperContent>
                {STEPS.map(({ label }) => (
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
