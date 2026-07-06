import { useEffect, useMemo, useState } from "react"

import { Loader2, Save } from "lucide-react"

import { cn } from "@/lib/utils"
import { Engine } from "@/util/const"
import { experimentPathToManifestRelative, safeDefaultSimulationPath } from "@/util/simulation"
import type { Simulation } from "@/util/types"
import { useCreateSimulation, useUpdateSimulation, type SimulationPayload } from "@/hooks/use-simulations"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import FileSelector from "@/components/FileSelector"

import SimulationPreview from "./SimulationPreview"

const GMX_OUTPUT_ROLES = ["structure", "trajectory"]
const AMBER_OUTPUT_ROLES = ["trajectory"]

interface SimulationEditorProps {
  experimentId: string
  engine: Engine
  selected: Simulation | null
  onSelect: (sim: Simulation | null) => void
  className?: string
}

const SimulationEditor = ({ experimentId, engine, selected, onSelect, className }: SimulationEditorProps) => {
  const isEditing = !!selected
  const isLocked = selected?.locked ?? false

  const [name, setName] = useState("")
  const [topology, setTopology] = useState("")
  const [coordinates, setCoordinates] = useState("")
  const [control, setControl] = useState("")
  const [outputs, setOutputs] = useState<Record<string, string>>({})
  const [extraArgs, setExtraArgs] = useState("")

  const createMutation = useCreateSimulation(experimentId)
  const updateMutation = useUpdateSimulation(experimentId)

  useEffect(() => {
    if (selected) {
      setName(selected.name)
      setTopology(selected.resolved_files.topology ?? selected.files.topology ?? "")
      setCoordinates(selected.resolved_files.coordinates ?? selected.files.coordinates ?? "")
      setControl(selected.resolved_files.control ?? selected.files.control ?? "")
      const out: Record<string, string> = {}
      for (const role of GMX_OUTPUT_ROLES) {
        if (selected.files[role]) out[role] = selected.files[role]
      }
      for (const role of AMBER_OUTPUT_ROLES) {
        if (selected.files[role]) out[role] = selected.files[role]
      }
      setOutputs(out)
      setExtraArgs(selected.extra_args ?? "")
    } else {
      setName("")
      setTopology("")
      setCoordinates("")
      setControl("")
      setOutputs({})
      setExtraArgs("")
    }
  }, [selected])

  const outputRoles = engine === Engine.GMX ? GMX_OUTPUT_ROLES : AMBER_OUTPUT_ROLES

  const simulationPath = selected?.simulation_path ?? safeDefaultSimulationPath(name)

  const buildFiles = useMemo(() => {
    const files: Record<string, string> = {
      topology: experimentPathToManifestRelative(topology, simulationPath),
    }
    if (engine === Engine.AMBER) {
      files.coordinates = experimentPathToManifestRelative(coordinates, simulationPath)
      files.control = experimentPathToManifestRelative(control, simulationPath)
    }
    for (const role of outputRoles) {
      if (outputs[role]) files[role] = outputs[role]
    }
    return files
  }, [topology, coordinates, control, outputs, engine, outputRoles, simulationPath])

  useEffect(() => {
    if (!isEditing) {
      const n = name || "protein"
      if (engine === Engine.GMX) {
        setOutputs({ structure: `${n}.gro`, trajectory: `${n}.xtc` })
      } else {
        setOutputs({ trajectory: `${n}.nc` })
      }
    }
  }, [name, isEditing, engine])

  const canSubmit = !!name && !!topology && (engine === Engine.GMX || (!!coordinates && !!control))

  const handleSubmit = () => {
    if (!canSubmit) return
    const payload: SimulationPayload = { name, files: buildFiles, extra_args: extraArgs }
    if (isEditing && selected) {
      updateMutation.mutate(
        { simulationPath: selected.simulation_path, payload },
        { onSuccess: (sim) => onSelect(sim) }
      )
    } else {
      createMutation.mutate(payload, { onSuccess: (sim) => onSelect(sim) })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  if (isLocked && selected) {
    return <SimulationPreview simulation={selected} title="Simulation" className={className} />
  }

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{isEditing ? "Edit Simulation" : "Create Simulation"}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="sim-name">Name</Label>
            <Input
              id="sim-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="protein"
              disabled={isLocked}
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium">Input files</span>
          <FileSelector
            experimentId={experimentId}
            ext={engine === Engine.GMX ? "tpr" : ["prmtop", "parm7"]}
            title="Topology"
            selectedPath={topology || null}
            onFileSelected={(file) => setTopology(file?.path ?? "")}
          />
          {engine === Engine.AMBER && (
            <>
              <FileSelector
                experimentId={experimentId}
                ext={["inpcrd", "rst7"]}
                title="Coordinates"
                selectedPath={coordinates || null}
                onFileSelected={(file) => setCoordinates(file?.path ?? "")}
              />
              <FileSelector
                experimentId={experimentId}
                ext={["mdin", "in"]}
                title="Run control"
                selectedPath={control || null}
                onFileSelected={(file) => setControl(file?.path ?? "")}
              />
            </>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium">Output files (relative paths)</span>
          {outputRoles.map((role: string) => (
            <div key={role} className="flex flex-col gap-1">
              <Label htmlFor={`out-${role}`}>{role}</Label>
              <Input
                id={`out-${role}`}
                value={outputs[role] ?? ""}
                onChange={(e) => setOutputs((prev) => ({ ...prev, [role]: e.target.value }))}
                disabled={isLocked}
              />
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-1">
          <Label htmlFor="extra-args">Extra arguments</Label>
          <Input
            id="extra-args"
            value={extraArgs}
            onChange={(e) => setExtraArgs(e.target.value)}
            placeholder="Additional CLI flags"
            disabled={isLocked}
          />
        </div>

        {selected && !selected.valid && (
          <p className="text-muted-foreground text-xs">
            This simulation has validation errors. Edit the fields above to repair it.
          </p>
        )}

        <div className="flex justify-end">
          <Button onClick={handleSubmit} disabled={!canSubmit || isPending || isLocked}>
            {isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
            {isEditing ? "Save" : "Create"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default SimulationEditor
