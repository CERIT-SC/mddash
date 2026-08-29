import { useGetNotebookConfig, useListExperiments } from "@/api/generated/client"
import { isNotebookActive } from "@/shared/pod-status"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import {
  Badge,
  Button,
  H1,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"
import { Link } from "@tanstack/react-router"
import { Plus } from "lucide-react"

import { ExperimentCard } from "./experiment-card"

export type DashboardSearch = {
  q?: string
  sort?: "oldest"
}

type DashboardProps = {
  search: DashboardSearch
  onSearchChange: (next: DashboardSearch) => void
}

function SectionHeading({ children, count, limit }: { children: string; count: number; limit?: number }) {
  return (
    <h2 className="text-text-muted flex items-center gap-2 text-sm font-medium tracking-wide uppercase">
      {children} <Badge variant="secondary">{limit === undefined ? count : `${count}/${limit}`}</Badge>
    </h2>
  )
}

export function Dashboard({ search, onSearchChange }: DashboardProps) {
  const query = useListExperiments({ query: { retry: false } })
  const config = useGetNotebookConfig({ query: { retry: false } })

  if (query.isError) {
    return <ApiErrorAlert error={query.error} onRetry={() => void query.refetch()} />
  }

  const experiments = query.data?.status === 200 ? query.data.data : undefined
  const concurrentLimit = config.data?.status === 200 ? config.data.data.concurrentLimit : undefined
  const q = search.q?.trim().toLowerCase() ?? ""

  const filtered = (experiments ?? [])
    .filter((experiment) => !q || experiment.name.toLowerCase().includes(q))
    .sort((a, b) =>
      search.sort === "oldest" ? a.created_at.localeCompare(b.created_at) : b.created_at.localeCompare(a.created_at)
    )

  const running = filtered.filter((experiment) => isNotebookActive(experiment.notebook?.status))
  const stopped = filtered.filter((experiment) => !isNotebookActive(experiment.notebook?.status))

  return (
    <section className="space-y-6 md:space-y-8">
      <div className="flex items-center gap-4">
        <H1>My Experiments</H1>
        <Button asChild>
          <Link to="/new">
            <Plus size={16} /> New
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <Tabs value="active">
          <TabsList>
            <TabsTrigger value="active">
              Active{" "}
              {experiments !== undefined && (
                <Badge variant="secondary" className="ml-2">
                  {experiments.length}
                </Badge>
              )}
            </TabsTrigger>
            {/* TODO: archived experiments are not available in the API yet */}
            <TabsTrigger value="archived" disabled>
              Archived
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="search"
            placeholder="Search experiments"
            className="w-56"
            value={search.q ?? ""}
            onChange={(event) => onSearchChange({ ...search, q: event.target.value || undefined })}
            aria-label="Search experiments"
          />
          <Select
            value={search.sort ?? "newest"}
            onValueChange={(value) => onSearchChange({ ...search, sort: value === "oldest" ? "oldest" : undefined })}
          >
            <SelectTrigger className="w-40" aria-label="Sort experiments">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest first</SelectItem>
              <SelectItem value="oldest">Oldest first</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {experiments === undefined ? (
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-44 rounded-xl" />
          ))}
        </div>
      ) : experiments.length === 0 ? (
        <p className="text-text-muted py-12 text-center">No experiments yet.</p>
      ) : filtered.length === 0 ? (
        <p className="text-text-muted py-12 text-center">{`No experiments match “${search.q}”.`}</p>
      ) : (
        <div className="space-y-8">
          {running.length > 0 && (
            <div className="space-y-4">
              <SectionHeading count={running.length} limit={concurrentLimit}>
                Notebook running
              </SectionHeading>
              <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
                {running.map((experiment) => (
                  <ExperimentCard key={experiment.id} experiment={experiment} />
                ))}
              </div>
            </div>
          )}
          {stopped.length > 0 && (
            <div className="space-y-4">
              <SectionHeading count={stopped.length}>Notebook stopped</SectionHeading>
              <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
                {stopped.map((experiment) => (
                  <ExperimentCard key={experiment.id} experiment={experiment} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
