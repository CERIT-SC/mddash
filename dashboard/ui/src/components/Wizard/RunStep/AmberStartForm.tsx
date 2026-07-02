import React, { useCallback } from "react"

import { Rocket } from "lucide-react"

import { SELECT_NONE } from "@/util/const"
import type { AmberBinary, EwaldPreset, Experiment } from "@/util/types"
import { useSubmitAmber } from "@/hooks/use-amber"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface AmberStartFormProps {
  experiment: Experiment
  nextStep: () => void
  changeStep: (step: number) => void
  simulationPath: string
  onStartJob: () => void
  binary?: AmberBinary
  ewald?: EwaldPreset
  np?: number
  ntomp?: number
}

const AmberStartForm = (props: AmberStartFormProps) => {
  const { experiment, simulationPath, onStartJob, binary, ewald, np, ntomp } = props

  const submitAmber = useSubmitAmber(experiment.id)

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const formData = new FormData(event.currentTarget)
      submitAmber.mutate(
        {
          simulationPath,
          binary: formData.get("binary") as string,
          ewald: formData.get("ewald") as string,
          np: parseInt(formData.get("np") as string),
          ntomp: parseInt(formData.get("ntomp") as string),
        },
        { onSuccess: () => onStartJob() }
      )
    },
    [simulationPath, onStartJob, submitAmber]
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Start AMBER simulation</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="binary-select">Binary</Label>
              <Select name="binary" defaultValue={binary ?? SELECT_NONE} required>
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
              <Select name="ewald" defaultValue={ewald ?? SELECT_NONE} required>
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
              <Input id="np-input" name="np" type="number" min={1} step={1} required defaultValue={np ?? ""} />
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="ntomp-input">OpenMP threads per MPI rank (ntomp)</Label>
              <Input id="ntomp-input" name="ntomp" type="number" min={1} step={1} required defaultValue={ntomp ?? ""} />
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
