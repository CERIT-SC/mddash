import { AlertCircle, Loader2, Lock, Plus } from "lucide-react"

import { cn } from "@/lib/utils"
import type { Simulation } from "@/util/types"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

export const CREATE_TAB = "_new"

interface SimulationTabsProps {
  simulations: Simulation[]
  /** Name of the selected simulation; null selects the create tab. */
  selectedName: string | null
  loading?: boolean
  onSelect: (simulationName: string) => void
  onCreate: () => void
  className?: string
}

const TRIGGER = cn(
  "border-border bg-muted text-muted-foreground relative h-9 max-w-64 min-w-28 flex-none rounded-t-md rounded-b-none border px-3 py-0 text-sm transition-colors",
  "hover:bg-secondary hover:text-secondary-foreground after:hidden",
  // `!` beats the repo TabsTrigger base group-variant rules (bg-transparent on active)
  "data-[state=active]:bg-card! data-[state=active]:text-foreground! data-[state=active]:border-b-transparent!"
)

const SimulationTabs = ({ simulations, selectedName, loading, onSelect, onCreate, className }: SimulationTabsProps) => {
  return (
    <Tabs
      value={selectedName ?? CREATE_TAB}
      onValueChange={(name) => (name === CREATE_TAB ? onCreate() : onSelect(name))}
      className={cn("w-full min-w-0 gap-0", className)}
    >
      <TabsList
        variant="line"
        aria-label="Simulations"
        className="simulation-tabs-scroll relative z-10 -mb-px h-auto w-full flex-nowrap items-end justify-start gap-1 overflow-x-auto rounded-none p-0"
      >
        {loading ? (
          <div className="text-muted-foreground flex h-9 items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading simulations
          </div>
        ) : (
          simulations.map((simulation) => (
            <TabsTrigger
              key={simulation.simulation_path}
              value={simulation.name}
              title={simulation.simulation_path}
              className={TRIGGER}
            >
              <span className="truncate font-medium">{simulation.name}</span>
              {simulation.locked && <Lock className="text-muted-foreground size-3.5 shrink-0" />}
              {!simulation.valid && <AlertCircle className="text-destructive size-3.5 shrink-0" />}
            </TabsTrigger>
          ))
        )}

        <TabsTrigger
          value={CREATE_TAB}
          title="Create new simulation setup"
          className="text-muted-foreground hover:text-foreground data-[state=active]:text-foreground! h-9 min-w-0 flex-none gap-1.5 border-transparent! bg-transparent px-2.5 shadow-none after:hidden data-[state=active]:bg-transparent!"
        >
          <Plus className="size-4" />
          <span className="hidden sm:inline">New setup</span>
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}

export default SimulationTabs
