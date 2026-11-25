import { ExperimentWizard, type WizardSearch } from "@/features/experiment"
import { createFileRoute, useNavigate } from "@tanstack/react-router"

export const Route = createFileRoute("/experiments/$experimentId")({
  validateSearch: (search: Record<string, unknown>): WizardSearch => ({
    simulation: typeof search.simulation === "string" && search.simulation !== "" ? search.simulation : undefined,
    source: search.source === "manual" || search.source === "notebook" ? search.source : undefined,
    trial: typeof search.trial === "string" && search.trial !== "" ? search.trial : undefined,
    mode: search.mode === "manual" ? "manual" : undefined,
    analysis: typeof search.analysis === "string" && search.analysis !== "" ? search.analysis : undefined,
    tab: search.tab === "analysis" ? "analysis" : undefined,
    publish: search.publish === true ? true : undefined,
  }),
  component: function WizardRoute() {
    const { experimentId } = Route.useParams()
    const search = Route.useSearch()
    const navigate = useNavigate({ from: Route.fullPath })
    return (
      <ExperimentWizard
        experimentId={experimentId}
        search={search}
        // Search-only updates must not bounce the viewport (e.g. picking a trial mid-table).
        onSearchChange={(next) => void navigate({ search: () => next, replace: true, resetScroll: false })}
      />
    )
  },
})
