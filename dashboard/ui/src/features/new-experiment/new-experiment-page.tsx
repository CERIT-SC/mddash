import { useState } from "react"

import { useListNotebookModules } from "@/api/generated/client"
import type { NotebookModule } from "@/api/generated/models"
import { asEngineFilter, ENGINE_LABELS, ENGINE_ORDER, ENGINE_TAB_VALUES, type EngineFilter } from "@/shared/engine"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Button, H1, H2, Skeleton, Tabs, TabsList, TabsTrigger } from "@e-infra/design-system"
import { Link } from "@tanstack/react-router"
import { ArrowLeft, SlidersHorizontal } from "lucide-react"

import { CreateExperimentDialog } from "./create-experiment-dialog"
import { WorkflowCard } from "./workflow-card"

export type NewExperimentSearch = { engine?: EngineFilter }

type NewExperimentPageProps = {
  search: NewExperimentSearch
  onSearchChange: (next: NewExperimentSearch) => void
  /** From validated runtime config — environment-derived values get no fallback defaults. */
  defaultNotebooksRepo: string
}

export function NewExperimentPage({ search, onSearchChange, defaultNotebooksRepo }: NewExperimentPageProps) {
  const modulesQuery = useListNotebookModules({ query: { retry: false } })
  const [selection, setSelection] = useState<NotebookModule | "custom" | null>(null)

  const modules = modulesQuery.data?.status === 200 ? modulesQuery.data.data : undefined
  const visibleEngines = ENGINE_ORDER.filter(
    (engine) => search.engine === undefined || ENGINE_TAB_VALUES[engine] === search.engine
  )
  const filteredEngine = search.engine === undefined ? undefined : visibleEngines[0]
  const visibleModules = modules?.filter((module) => visibleEngines.includes(module.engine))

  return (
    <section className="space-y-6 md:space-y-8">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/" aria-label="Back to My Experiments">
              <ArrowLeft size={18} />
            </Link>
          </Button>
          <H1>New Experiment</H1>
        </div>
        <H2>Select a Workflow</H2>
        <p className="text-text-muted max-w-2xl">
          A workflow is a set of notebooks that prepares and runs your simulation. Start from a curated one, or bring
          your own git repository.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <Tabs
          value={search.engine ?? "all"}
          onValueChange={(value) => onSearchChange({ engine: asEngineFilter(value) })}
        >
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            {ENGINE_ORDER.map((engine) => (
              <TabsTrigger key={engine} value={ENGINE_TAB_VALUES[engine]}>
                {ENGINE_LABELS[engine]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {/* Custom stays available even when the catalog fetch fails — it needs no catalog data. */}
        <Button variant="outline" onClick={() => setSelection("custom")}>
          <SlidersHorizontal size={16} /> Use custom workflow
        </Button>
      </div>

      {modules === undefined && modulesQuery.isPending && (
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="Loading workflows">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-44 rounded-xl" />
          ))}
        </div>
      )}
      {modulesQuery.isError && <ApiErrorAlert error={modulesQuery.error} onRetry={() => void modulesQuery.refetch()} />}
      {visibleModules !== undefined &&
        (visibleModules.length > 0 ? (
          <div className="space-y-8">
            {visibleEngines.map((engine) => {
              const engineModules = visibleModules.filter((module) => module.engine === engine)
              if (engineModules.length === 0) return null
              return (
                <div key={engine} className="space-y-4">
                  <h3 className="text-text-muted text-sm font-medium tracking-wide uppercase">
                    {ENGINE_LABELS[engine]}
                  </h3>
                  <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {engineModules.map((module) => (
                      <WorkflowCard key={module.id} module={module} onSelect={() => setSelection(module)} />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-text-muted py-12 text-center">
            {filteredEngine === undefined
              ? "No workflows available."
              : `No ${ENGINE_LABELS[filteredEngine]} workflows available.`}
          </p>
        ))}

      <CreateExperimentDialog
        selection={selection}
        onClose={() => setSelection(null)}
        defaultNotebooksRepo={defaultNotebooksRepo}
      />
    </section>
  )
}
