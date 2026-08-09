import { AlertCircle, Loader2, Lock, Plus } from "lucide-react"

import { cn } from "@/lib/utils"
import type { Simulation } from "@/util/types"

interface SimulationTabsProps {
  simulations: Simulation[]
  /** Name of the selected simulation; null selects the create tab. */
  selectedName: string | null
  loading?: boolean
  onSelect: (simulationName: string) => void
  onCreate: () => void
  className?: string
}

const SimulationTabs = ({ simulations, selectedName, loading, onSelect, onCreate, className }: SimulationTabsProps) => {
  const createSelected = selectedName === null

  return (
    <div className={cn("w-full min-w-0", className)}>
      <div
        role="tablist"
        aria-label="Simulations"
        className="simulation-tabs-scroll flex items-center gap-2 overflow-x-auto px-2"
      >
        {loading ? (
          <div className="text-muted-foreground flex h-8 items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading simulations
          </div>
        ) : (
          simulations.map((simulation) => {
            const isSelected = simulation.name === selectedName
            return (
              <button
                key={simulation.simulation_path}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => onSelect(simulation.name)}
                title={simulation.simulation_path}
                className={cn(
                  "bg-secondary text-secondary-foreground hover:bg-secondary/80 focus-visible:ring-ring flex h-8 max-w-64 min-w-28 items-center gap-2 rounded-md px-2.5 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:outline-hidden",
                  isSelected && "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground"
                )}
              >
                <span className="truncate font-medium">{simulation.name}</span>
                {simulation.locked && <Lock className="text-muted-foreground h-3.5 w-3.5 shrink-0" />}
                {!simulation.valid && <AlertCircle className="text-destructive h-3.5 w-3.5 shrink-0" />}
              </button>
            )
          })
        )}

        <button
          type="button"
          role="tab"
          aria-selected={createSelected}
          className={cn(
            "border-border bg-background text-muted-foreground hover:bg-secondary hover:text-secondary-foreground focus-visible:ring-ring flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-hidden",
            createSelected && "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground"
          )}
          onClick={onCreate}
          title="Create new simulation setup"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">New setup</span>
        </button>
      </div>
    </div>
  )
}

export default SimulationTabs
