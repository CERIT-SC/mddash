import { ExperimentWizard, type WizardSearch } from "@/features/experiment/wizard"
import { createFileRoute, useNavigate } from "@tanstack/react-router"

export const Route = createFileRoute("/experiments/$experimentId")({
  validateSearch: (search: Record<string, unknown>): WizardSearch => ({
    simulation: typeof search.simulation === "string" && search.simulation !== "" ? search.simulation : undefined,
    step:
      typeof search.step === "number" && Number.isInteger(search.step) && search.step >= 0 && search.step <= 4
        ? search.step
        : undefined,
  }),
  component: function WizardRoute() {
    const { experimentId } = Route.useParams()
    const search = Route.useSearch()
    const navigate = useNavigate({ from: Route.fullPath })
    return (
      <ExperimentWizard
        experimentId={experimentId}
        search={search}
        onSearchChange={(next) => void navigate({ search: () => next, replace: true })}
      />
    )
  },
})
