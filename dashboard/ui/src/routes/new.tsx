import { NewExperimentPage, type NewExperimentSearch } from "@/features/new-experiment"
import { createFileRoute, useNavigate } from "@tanstack/react-router"

export const Route = createFileRoute("/new")({
  validateSearch: (search: Record<string, unknown>): NewExperimentSearch => ({
    engine: search.engine === "gmx" || search.engine === "amber" ? search.engine : undefined,
  }),
  component: function NewExperimentRoute() {
    const search = Route.useSearch()
    const navigate = useNavigate({ from: Route.fullPath })
    const { config } = Route.useRouteContext()
    return (
      <NewExperimentPage
        search={search}
        onSearchChange={(next) => void navigate({ search: next, replace: true })}
        defaultNotebooksRepo={config.defaultNotebooksRepo}
      />
    )
  },
})
