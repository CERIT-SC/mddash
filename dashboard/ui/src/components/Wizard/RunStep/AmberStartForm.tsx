import React, { useCallback, useMemo, useState } from "react"

import { Plus, Rocket, X } from "lucide-react"
import { toast } from "sonner"

import { SELECT_NONE } from "@/util/const"
import type { AmberBinary, EwaldPreset } from "@/util/types"
import { useSubmitAmber } from "@/hooks/use-amber"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const PMEMD_ARGUMENTS = [
  { key: "A", type: "boolean", description: "Append to existing output files instead of overwriting" },
  { key: "inf", type: "text", description: "MD info/progress file (default: mdinfo)" },
  { key: "l", type: "text", description: "Log file for simulation output" },
  { key: "v", type: "text", description: "Velocity trajectory file" },
  { key: "frc", type: "text", description: "Force trajectory file" },
  { key: "e", type: "text", description: "Per-step energy data file" },
  { key: "ref", type: "text", description: "Reference coordinate file for restraints (requires ntr=1 in mdin)" },
  { key: "ng", type: "number", description: "Number of replica groups (REMD)" },
  { key: "rem", type: "number", description: "Replica exchange method: 0=none, 1=T-REMD, -1=M-REMD" },
  { key: "groupfile", type: "text", description: "Per-replica command-line argument file (REMD)" },
  { key: "remlog", type: "text", description: "Replica exchange log file" },
  { key: "remtype", type: "text", description: "M-REMD dimension definition file" },
  { key: "AllowSmallBox", type: "boolean", description: "Override GPU small-box safety check (use with caution)" },
] as const

interface AmberStartFormProps extends WizardStepProps {
  prmtopName: string
  inpcrdName: string
  mdinName: string
  onStartJob: () => void
  binary?: AmberBinary
  ewald?: EwaldPreset
  np?: number
  ntomp?: number
}

const AmberStartForm = (props: AmberStartFormProps) => {
  const { experiment, prmtopName, inpcrdName, mdinName, onStartJob, binary, ewald, np, ntomp } = props

  const submitAmber = useSubmitAmber(experiment.id)

  const [selectedArgument, setSelectedArgument] = useState(SELECT_NONE)
  const [argumentValue, setArgumentValue] = useState("")
  const [addedArguments, setAddedArguments] = useState<Array<{ key: string; value: string; description: string }>>([])

  const selectedArgConfig = useMemo(
    () => PMEMD_ARGUMENTS.find((arg) => arg.key === selectedArgument),
    [selectedArgument]
  )

  const availableArguments = useMemo(
    () => PMEMD_ARGUMENTS.filter((arg) => !addedArguments.some((added) => added.key === arg.key)),
    [addedArguments]
  )

  const isAddDisabled = useMemo(() => {
    if (!selectedArgument || selectedArgument === SELECT_NONE) return true
    if (selectedArgConfig?.type === "boolean") return false
    return !argumentValue.trim()
  }, [selectedArgument, selectedArgConfig, argumentValue])

  const handleSelectArgument = useCallback((value: string) => {
    setSelectedArgument(value)
    setArgumentValue("")
  }, [])

  const handleAddArgument = useCallback(() => {
    if (!selectedArgument || selectedArgument === SELECT_NONE || !selectedArgConfig) return

    if (addedArguments.some((arg) => arg.key === selectedArgument)) {
      toast.warning("Argument already added")
      return
    }

    setAddedArguments((prev) => [
      ...prev,
      { key: selectedArgument, value: argumentValue.trim(), description: selectedArgConfig.description },
    ])
    setSelectedArgument(SELECT_NONE)
    setArgumentValue("")
  }, [selectedArgument, selectedArgConfig, argumentValue, addedArguments])

  const handleDeleteArgument = useCallback((keyToDelete: string) => {
    setAddedArguments((prev) => prev.filter((arg) => arg.key !== keyToDelete))
  }, [])

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const formData = new FormData(event.currentTarget)
      const extraArgs = addedArguments.map((arg) => (arg.value ? `-${arg.key} ${arg.value}` : `-${arg.key}`)).join(" ")
      formData.set("extra_args", extraArgs)
      submitAmber.mutate({ prmtopName, formData }, { onSuccess: () => onStartJob() })
    },
    [prmtopName, addedArguments, onStartJob, submitAmber]
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Start AMBER simulation</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input type="hidden" name="inpcrd_name" value={inpcrdName} />
          <input type="hidden" name="mdin_name" value={mdinName} />
          {!!np && <input type="hidden" name="np" value={np} />}
          {!!ntomp && <input type="hidden" name="ntomp" value={ntomp} />}
          {binary && <input type="hidden" name="binary" value={binary} />}
          {ewald && <input type="hidden" name="ewald" value={ewald} />}

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="binary-select">Binary</Label>
              <Select name="binary" defaultValue={binary ?? SELECT_NONE} disabled={!!binary} required>
                <SelectTrigger id="binary-select">
                  <SelectValue placeholder="Select binary" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_NONE} disabled>
                    <em>Select...</em>
                  </SelectItem>
                  <SelectItem value="pmemd.cuda">pmemd.cuda (GPU)</SelectItem>
                  <SelectItem value="pmemd.MPI">pmemd.MPI (CPU)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="ewald-select">Ewald Preset</Label>
              <Select name="ewald" defaultValue={ewald ?? SELECT_NONE} disabled={!!ewald} required>
                <SelectTrigger id="ewald-select">
                  <SelectValue placeholder="Select preset" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_NONE} disabled>
                    <em>Select...</em>
                  </SelectItem>
                  <SelectItem value="default">Default</SelectItem>
                  <SelectItem value="optimized">Optimized</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="np-input">Number of MPI processes (np)</Label>
              <Input
                id="np-input"
                name="np"
                type="number"
                min={1}
                step={1}
                required
                defaultValue={np ?? ""}
                disabled={!!np}
              />
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="ntomp-input">OpenMP threads per MPI rank (ntomp)</Label>
              <Input
                id="ntomp-input"
                name="ntomp"
                type="number"
                min={1}
                step={1}
                required
                defaultValue={ntomp ?? ""}
                disabled={!!ntomp}
              />
            </div>
          </div>

          {/* Additional pmemd arguments */}
          <div className="flex flex-col gap-2">
            <Label>Additional pmemd arguments</Label>

            <div className="flex flex-wrap items-end gap-2">
              <div className="flex min-w-48 flex-1 flex-col gap-1">
                <Select value={selectedArgument} onValueChange={handleSelectArgument}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select argument" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SELECT_NONE}>
                      <em>Select argument</em>
                    </SelectItem>
                    {availableArguments.map((arg) => (
                      <SelectItem key={arg.key} value={arg.key}>
                        -{arg.key} — {arg.description}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedArgConfig?.type === "boolean" ? (
                <p className="text-muted-foreground flex-1 self-center text-sm">Boolean flag (no value required)</p>
              ) : (
                <div className="min-w-32 flex-1">
                  <Input
                    placeholder="Value"
                    value={argumentValue}
                    type={selectedArgConfig?.type === "number" ? "number" : "text"}
                    onChange={(e) => setArgumentValue(e.target.value)}
                  />
                </div>
              )}

              <Button type="button" variant="default" onClick={handleAddArgument} disabled={isAddDisabled}>
                <Plus className="mr-1 h-4 w-4" />
                Add
              </Button>
            </div>

            <div className="flex flex-col gap-1">
              <p className="text-muted-foreground text-xs">Added arguments:</p>
              <div className="flex flex-wrap gap-1">
                {addedArguments.length === 0 ? (
                  <p className="text-muted-foreground text-xs italic">No arguments added</p>
                ) : (
                  addedArguments.map((arg) => (
                    <Badge key={arg.key} variant="outline" className="gap-1">
                      -{arg.key} {arg.value}
                      <button
                        type="button"
                        onClick={() => handleDeleteArgument(arg.key)}
                        className="hover:text-destructive ml-1"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="mt-2 flex justify-end">
            <Button type="submit" disabled={submitAmber.isPending}>
              <Rocket className="mr-1 h-4 w-4" />
              Run
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

export default AmberStartForm
