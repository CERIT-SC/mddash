import React, { useCallback } from "react"

import { Rocket } from "lucide-react"

import { SELECT_NONE } from "@/util/const"
import { useSubmitGmx } from "@/hooks/use-gromacs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

interface ManualStartFormProps extends WizardStepProps {
  simulationPath: string
  onStartJob: () => void
  np?: number
  ntomp?: number
  nb?: "cpu" | "gpu" | "auto"
  pme?: "cpu" | "gpu" | "auto"
}

export const StartForm = (props: ManualStartFormProps) => {
  const { experiment, simulationPath, onStartJob, np, ntomp, nb, pme } = props

  const submitGmx = useSubmitGmx(experiment.id)

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()

      const formData = new FormData(event.currentTarget)
      submitGmx.mutate(
        {
          simulationPath,
          np: parseInt(formData.get("np") as string),
          ntomp: parseInt(formData.get("ntomp") as string),
          pme: formData.get("pme") as string,
          nb: formData.get("nb") as string,
        },
        { onSuccess: () => onStartJob() }
      )
    },
    [simulationPath, onStartJob, submitGmx]
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Start simulation</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="np-input">Number of MPI processes (np)</Label>
              <Input id="np-input" name="np" type="number" min={1} step={1} required defaultValue={np || ""} />
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="ntomp-input">OpenMP threads per MPI rank (-ntomp)</Label>
              <Input id="ntomp-input" name="ntomp" type="number" min={0} step={1} required defaultValue={ntomp || ""} />
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="nb-select">Device type for non-bonded interactions (-nb)</Label>
              <Select name="nb" defaultValue={nb || SELECT_NONE} required>
                <SelectTrigger id="nb-select">
                  <SelectValue placeholder="Select device" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_NONE} disabled>
                    <em>Select...</em>
                  </SelectItem>
                  <SelectItem value="cpu">CPU</SelectItem>
                  <SelectItem value="gpu">GPU</SelectItem>
                  <SelectItem value="auto">Auto</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1">
              <Label htmlFor="pme-select">Device type for PME calculations (-pme)</Label>
              <Select name="pme" defaultValue={pme || SELECT_NONE} required>
                <SelectTrigger id="pme-select">
                  <SelectValue placeholder="Select device" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_NONE} disabled>
                    <em>Select...</em>
                  </SelectItem>
                  <SelectItem value="cpu">CPU</SelectItem>
                  <SelectItem value="gpu">GPU</SelectItem>
                  <SelectItem value="auto">Auto</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="mt-2 flex justify-end">
            <Button type="submit" disabled={submitGmx.isPending}>
              <Rocket className="mr-1 h-4 w-4" />
              Run
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

export default StartForm
