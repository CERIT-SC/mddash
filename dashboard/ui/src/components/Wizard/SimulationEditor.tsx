import { useEffect, useMemo, useState } from "react"

import { Loader2, Save, Trash2 } from "lucide-react"

import { cn } from "@/lib/utils"
import { Engine } from "@/util/const"
import type { Simulation } from "@/util/types"
import {
  useCreateSimulation,
  useDeleteSimulation,
  useUpdateSimulation,
  type SimulationPayload,
} from "@/hooks/use-simulations"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ConfirmDialog from "@/components/ConfirmDialog"
import FileSelector from "@/components/FileSelector"

import SimulationPreview from "./SimulationPreview"

const ROLE_HELP: Record<string, string> = {
  run_input: "GROMACS run input file (.tpr) used to start the simulation.",
  topology: "AMBER topology file (.prmtop).",
  coordinates: "AMBER coordinate file (.rst7).",
  control: "AMBER run control file (.mdin).",
  reference_structure: "Structure matching the trajectory atom set and order. Created by the setup notebook.",
  trajectory: "Trajectory file. Auto-filled from run input name.",
  run_structure: "Final coordinate snapshot from the run. Auto-filled from run input name.",
  name: "Identifier for this simulation setup.",
  extra_args: "Additional GROMACS/AMBER CLI flags passed to mdrun.",
}

interface SimulationEditorProps {
  experimentId: string
  engine: Engine
  selected: Simulation | null
  onSelect: (sim: Simulation | null) => void
  className?: string
}

function dirname(path: string): string {
  const index = path.lastIndexOf("/")
  return index === -1 ? "" : path.slice(0, index)
}

function stem(path: string): string {
  const name = path.split("/").pop() ?? path
  const index = name.lastIndexOf(".")
  return index === -1 ? name : name.slice(0, index)
}

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name
}

const SimulationEditor = ({ experimentId, engine, selected, onSelect, className }: SimulationEditorProps) => {
  const isEditing = !!selected
  const isLocked = selected?.locked ?? false

  const [name, setName] = useState("")
  const [runInput, setRunInput] = useState("")
  const [coordinates, setCoordinates] = useState("")
  const [control, setControl] = useState("")
  const [referenceStructure, setReferenceStructure] = useState("")
  const [trajectory, setTrajectory] = useState("")
  const [runStructure, setRunStructure] = useState("")
  const [extraArgs, setExtraArgs] = useState("")
  const [deleteDialog, setDeleteDialog] = useState(false)

  const createMutation = useCreateSimulation(experimentId)
  const updateMutation = useUpdateSimulation(experimentId)
  const deleteMutation = useDeleteSimulation(experimentId)

  useEffect(() => {
    if (selected) {
      setName(selected.name)
      const inputKey = engine === Engine.GMX ? "run_input" : "topology"
      setRunInput(selected.resolved_files[inputKey] ?? selected.files[inputKey] ?? "")
      setCoordinates(selected.resolved_files.coordinates ?? selected.files.coordinates ?? "")
      setControl(selected.resolved_files.control ?? selected.files.control ?? "")
      setReferenceStructure(selected.resolved_files.reference_structure ?? selected.files.reference_structure ?? "")
      setTrajectory(selected.resolved_files.trajectory ?? selected.files.trajectory ?? "")
      setRunStructure(selected.resolved_files.run_structure ?? selected.files.run_structure ?? "")
      setExtraArgs(selected.extra_args ?? "")
    } else {
      setName("")
      setRunInput("")
      setCoordinates("")
      setControl("")
      setReferenceStructure("")
      setTrajectory("")
      setRunStructure("")
      setExtraArgs("")
    }
  }, [selected, engine])

  // AMBER writes outputs next to its control file; GROMACS writes them next to its run input.
  useEffect(() => {
    const outputInput = engine === Engine.GMX ? runInput : control
    if (isEditing || !outputInput) return

    const base = stem(outputInput)
    const dir = dirname(outputInput)
    if (!name) setName(base)
    if (!trajectory) setTrajectory(joinPath(dir, `${base}.${engine === Engine.GMX ? "xtc" : "nc"}`))
    if (engine === Engine.GMX && !runStructure) setRunStructure(joinPath(dir, `${base}.gro`))
    if (!referenceStructure) setReferenceStructure(`analysis/${base}-reference.gro`)
  }, [runInput, control, isEditing, engine]) // eslint-disable-line react-hooks/exhaustive-deps

  const buildFiles = useMemo(() => {
    const files: Record<string, string> = {}
    if (engine === Engine.GMX) {
      files.run_input = runInput
      if (runStructure) files.run_structure = runStructure
    } else {
      files.topology = runInput
      files.coordinates = coordinates
      files.control = control
    }
    if (referenceStructure) files.reference_structure = referenceStructure
    if (trajectory) files.trajectory = trajectory
    return files
  }, [runInput, coordinates, control, referenceStructure, trajectory, runStructure, engine])

  const canSubmit =
    !!name &&
    !!runInput &&
    !!referenceStructure &&
    !!trajectory &&
    (engine === Engine.GMX || (!!coordinates && !!control))

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

  const handleDelete = () => {
    if (!selected) return
    deleteMutation.mutate(selected.simulation_path, {
      onSuccess: () => onSelect(null),
    })
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  if (isLocked && selected) {
    return (
      <>
        <SimulationPreview simulation={selected} title="Simulation" className={className} />
        <div className="mt-3 flex justify-end">
          <Button
            variant="outline"
            className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
            onClick={() => setDeleteDialog(true)}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete simulation
          </Button>
        </div>
        <ConfirmDialog
          open={deleteDialog}
          setOpen={setDeleteDialog}
          title="Delete simulation"
          message="Delete this simulation and all related jobs? This cannot be undone."
          onConfirm={handleDelete}
        />
      </>
    )
  }

  return (
    <>
      <Card className={cn(className)}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{isEditing ? "Edit Simulation" : "Create Simulation"}</CardTitle>
            {isEditing && (
              <Button
                variant="outline"
                size="sm"
                className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
                onClick={() => setDeleteDialog(true)}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="mr-1 h-4 w-4" />
                Delete
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Name */}
          <div className="flex flex-col gap-1">
            <Label htmlFor="sim-name">Name</Label>
            <Input id="sim-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="protein" />
            <p className="text-muted-foreground text-xs">{ROLE_HELP.name}</p>
          </div>

          {/* Existing files — files that already exist and are selected from disk */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <p className="text-muted-foreground/80 col-span-full text-[11px] tracking-wide uppercase">Existing files</p>

            <FileSelector
              experimentId={experimentId}
              ext={engine === Engine.GMX ? "tpr" : ["prmtop", "parm7"]}
              title={engine === Engine.GMX ? "Run input (.tpr)" : "Topology"}
              selectedPath={runInput || null}
              onFileSelected={(file) => setRunInput(file?.path ?? "")}
              helperText={engine === Engine.GMX ? ROLE_HELP.run_input : ROLE_HELP.topology}
            />

            <FileSelector
              experimentId={experimentId}
              ext={["gro", "pdb"]}
              title="Reference structure"
              selectedPath={referenceStructure || null}
              onFileSelected={(file) => setReferenceStructure(file?.path ?? "")}
              helperText={ROLE_HELP.reference_structure}
            />

            {engine === Engine.AMBER && (
              <>
                <FileSelector
                  experimentId={experimentId}
                  ext={["inpcrd", "rst7"]}
                  title="Coordinates"
                  selectedPath={coordinates || null}
                  onFileSelected={(file) => setCoordinates(file?.path ?? "")}
                  helperText={ROLE_HELP.coordinates}
                />
                <FileSelector
                  experimentId={experimentId}
                  ext={["mdin", "in"]}
                  title="Run control"
                  selectedPath={control || null}
                  onFileSelected={(file) => setControl(file?.path ?? "")}
                  helperText={ROLE_HELP.control}
                />
              </>
            )}
          </div>

          {/* Output paths — paths the simulation will create */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <p className="text-muted-foreground/80 col-span-full text-[11px] tracking-wide uppercase">Output paths</p>

            <div className="flex flex-col gap-1">
              <Label htmlFor="trajectory">Trajectory</Label>
              <Input
                id="trajectory"
                value={trajectory}
                onChange={(e) => setTrajectory(e.target.value)}
                placeholder="production/protein.xtc"
              />
              <p className="text-muted-foreground text-xs">{ROLE_HELP.trajectory}</p>
            </div>

            {engine === Engine.GMX && (
              <div className="flex flex-col gap-1">
                <Label htmlFor="run-structure">Final run structure</Label>
                <Input
                  id="run-structure"
                  value={runStructure}
                  onChange={(e) => setRunStructure(e.target.value)}
                  placeholder="production/protein.gro"
                />
                <p className="text-muted-foreground text-xs">{ROLE_HELP.run_structure}</p>
              </div>
            )}
          </div>

          {/* Extra arguments */}
          <div className="flex flex-col gap-1">
            <p className="text-muted-foreground/80 mb-1 text-[11px] tracking-wide uppercase">Runtime options</p>
            <Label htmlFor="extra-args" className="sr-only">
              Extra arguments
            </Label>
            <Input
              id="extra-args"
              value={extraArgs}
              onChange={(e) => setExtraArgs(e.target.value)}
              placeholder="Additional CLI flags"
            />
            <p className="text-muted-foreground text-xs">{ROLE_HELP.extra_args}</p>
          </div>

          {selected && !selected.valid && (
            <p className="text-muted-foreground text-xs">
              This simulation has validation errors. Edit the fields above to repair it.
            </p>
          )}

          <div className="flex justify-end">
            <Button onClick={handleSubmit} disabled={!canSubmit || isPending}>
              {isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
              {isEditing ? "Save" : "Create"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteDialog}
        setOpen={setDeleteDialog}
        title="Delete simulation"
        message="Delete this simulation and all related jobs? This cannot be undone."
        onConfirm={handleDelete}
      />
    </>
  )
}

export default SimulationEditor
