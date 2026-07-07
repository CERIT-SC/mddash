import { AlertCircle, Lock } from "lucide-react"

import { cn } from "@/lib/utils"
import type { Simulation } from "@/util/types"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const ROLE_LABELS: Record<string, string> = {
  run_input: "Run input",
  run_structure: "Final run structure",
  reference_structure: "Reference structure",
  topology: "Topology",
  coordinates: "Coordinates",
  control: "Run control",
  trajectory: "Trajectory",
}

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
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="bg-muted/40 rounded-md border p-3">
            <span className="text-muted-foreground text-xs">Name</span>
            <p className="mt-1 text-sm font-medium">{simulation.name}</p>
          </div>
          <div className="bg-muted/40 rounded-md border p-3">
            <span className="text-muted-foreground text-xs">Path</span>
            <p className="text-muted-foreground mt-1 truncate text-sm" title={simulation.simulation_path}>
              {simulation.simulation_path}
            </p>
          </div>
        </div>

        <div className="rounded-md border">
          <div className="border-border bg-muted/40 border-b px-3 py-2">
            <span className="text-sm font-medium">Files</span>
          </div>
          <div className="divide-border divide-y">
            {Object.entries(simulation.files).map(([role, path]) => {
              const missing = simulation.missing_files.includes(role)
              return (
                <div key={role} className="grid gap-2 px-3 py-2 text-sm sm:grid-cols-[8rem_1fr_auto] sm:items-center">
                  <span className="font-medium">{ROLE_LABELS[role] ?? role}</span>
                  <span className="text-muted-foreground min-w-0 truncate" title={path}>
                    {path}
                  </span>
                  <Badge variant={missing ? "destructive" : "outline"} className="w-fit text-xs">
                    {missing ? "missing" : "present"}
                  </Badge>
                </div>
              )
            })}
          </div>
        </div>
        {simulation.extra_args && (
          <div className="rounded-md border">
            <div className="border-border bg-muted/40 border-b px-3 py-2">
              <span className="text-sm font-medium">Extra args</span>
            </div>
            <code className="bg-muted/30 block rounded-b-md px-3 py-2 text-xs break-all">{simulation.extra_args}</code>
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
