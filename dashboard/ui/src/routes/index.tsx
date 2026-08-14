import { Dashboard, type DashboardSearch } from "@/features/dashboard/dashboard"
import { createFileRoute, useNavigate } from "@tanstack/react-router"

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): DashboardSearch => ({
    q: typeof search.q === "string" && search.q !== "" ? search.q : undefined,
    sort: search.sort === "oldest" ? "oldest" : undefined,
  }),
  component: function DashboardRoute() {
    const search = Route.useSearch()
    const navigate = useNavigate({ from: "/" })
    return <Dashboard search={search} onSearchChange={(next) => void navigate({ search: next, replace: true })} />
  },
})
