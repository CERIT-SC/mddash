import { Loader2, Lock } from "lucide-react"

import { cn } from "@/lib/utils"
import type { Simulation } from "@/util/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface SimulationSelectorProps {
  simulations: Simulation[]
  selectedPath: string | null
  loading?: boolean
  onSelect: (simulation: Simulation | null) => void
  className?: string
}

const SimulationSelector = ({ simulations, selectedPath, loading, onSelect, className }: SimulationSelectorProps) => {
  if (loading) {
    return (
      <Card className={cn("w-72 shrink-0", className)}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="text-muted-foreground h-5 w-5 animate-spin" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn("w-72 shrink-0", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Simulations</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {simulations.length === 0 ? (
          <p className="text-muted-foreground text-sm italic">No simulations found.</p>
        ) : (
          simulations.map((sim) => {
            const isSelected = sim.simulation_path === selectedPath
            return (
              <button
                key={sim.simulation_path}
                type="button"
                onClick={() => onSelect(isSelected ? null : sim)}
                className={cn(
                  "hover:bg-accent flex w-full flex-col gap-1 rounded-md border p-2 text-left transition-colors",
                  isSelected && "border-primary bg-accent"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{sim.name}</span>
                  {sim.locked && <Lock className="text-muted-foreground h-3 w-3 shrink-0" />}
                </div>
                <div className="flex flex-wrap gap-1">
                  <Badge variant="outline" className="text-xs">
                    {sim.engine}
                  </Badge>
                  {!sim.valid && (
                    <Badge variant="destructive" className="text-xs">
                      invalid
                    </Badge>
                  )}
                </div>
                <span className="text-muted-foreground truncate text-xs">{sim.simulation_path}</span>
              </button>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}

export default SimulationSelector
