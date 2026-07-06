import { AlertCircle, Lock } from "lucide-react"

import { cn } from "@/lib/utils"
import type { Simulation } from "@/util/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface SimulationPreviewProps {
  simulation: Simulation | null
  loading?: boolean
  title?: string
  className?: string
}

const SimulationPreview = ({ simulation, loading, title = "Simulation", className }: SimulationPreviewProps) => {
  if (loading) {
    return (
      <Card className={cn(className)}>
        <CardContent className="text-muted-foreground py-4 text-sm">Loading simulation...</CardContent>
      </Card>
    )
  }

  if (!simulation) {
    return (
      <Card className={cn(className)}>
        <CardContent className="text-muted-foreground py-4 text-sm">No simulation selected.</CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{title}</CardTitle>
          <div className="flex gap-1">
            <Badge variant="outline">{simulation.engine}</Badge>
            {simulation.locked && (
              <Badge variant="secondary">
                <Lock className="mr-1 h-3 w-3" />
                locked
              </Badge>
            )}
            {simulation.valid ? <Badge variant="outline">valid</Badge> : <Badge variant="destructive">invalid</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-xs">Name</span>
          <span className="text-sm font-medium">{simulation.name}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-xs">Path</span>
          <span className="text-muted-foreground text-sm">{simulation.simulation_path}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-xs">Files</span>
          <div className="flex flex-col gap-1">
            {Object.entries(simulation.files).map(([role, path]) => {
              const missing = simulation.missing_files.includes(role)
              return (
                <div key={role} className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="text-xs">
                    {role}
                  </Badge>
                  <span className="text-muted-foreground">{path}</span>
                  {missing && (
                    <Badge variant="destructive" className="text-xs">
                      missing
                    </Badge>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        {simulation.extra_args && (
          <div className="flex flex-col gap-1">
            <span className="text-muted-foreground text-xs">Extra args</span>
            <code className="bg-muted rounded px-2 py-1 text-xs">{simulation.extra_args}</code>
          </div>
        )}
        {!simulation.valid && simulation.errors.length > 0 && (
          <div className="border-destructive bg-destructive/10 text-destructive flex items-start gap-2 rounded-md border p-2 text-xs">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div className="flex flex-col gap-0.5">
              {simulation.errors.map((err, i) => (
                <span key={i}>{err}</span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default SimulationPreview
