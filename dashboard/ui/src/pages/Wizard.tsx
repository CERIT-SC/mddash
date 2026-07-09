import React, { useState } from "react"

import { useParams } from "@tanstack/react-router"
import { Check, Loader2, Pencil, X } from "lucide-react"

import { useEditExperiment, useExperiment } from "@/hooks/use-experiment"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import WizardStepper from "@/components/Wizard/Stepper"

const Wizard = () => {
  const { id } = useParams({ from: "/$id/wizard" })
  const { data: experiment, isLoading } = useExperiment(id)
  const editExperiment = useEditExperiment()

  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState("")

  const handleEditClick = () => {
    if (experiment) {
      setNameInput(experiment.name)
      setEditingName(true)
    }
  }

  const handleNameSave = async () => {
    if (experiment && nameInput.trim() && nameInput !== experiment.name) {
      editExperiment.mutate({
        id: experiment.id,
        data: { name: nameInput.trim() },
      })
    }
    setEditingName(false)
  }

  const handleNameCancel = () => {
    setEditingName(false)
    setNameInput("")
  }

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleNameSave()
    else if (e.key === "Escape") handleNameCancel()
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">Wizard</h1>

      <div className="flex items-center justify-center" style={{ minHeight: 56 }}>
        {isLoading ? (
          <p className="text-muted-foreground">Loading...</p>
        ) : experiment ? (
          <Card className="flex items-center px-4 py-2">
            {editingName ? (
              <div className="flex items-center gap-1">
                <Input
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onBlur={handleNameSave}
                  onKeyDown={handleNameKeyDown}
                  autoFocus
                  className="max-w-xl min-w-64"
                />
                <Button variant="ghost" size="icon" aria-label="Save" onClick={handleNameSave}>
                  <Check className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" aria-label="Cancel" onClick={handleNameCancel}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <span className="mr-1 text-lg font-semibold">{experiment.name}</span>
                <Button variant="ghost" size="icon" aria-label="Edit name" onClick={handleEditClick}>
                  <Pencil className="h-4 w-4" />
                </Button>
              </div>
            )}
          </Card>
        ) : null}
      </div>

      {isLoading ? (
        <div className="mt-6 flex justify-center">
          <Loader2 className="text-muted-foreground h-10 w-10 animate-spin" />
        </div>
      ) : experiment ? (
        <div className="mt-2 px-2 sm:px-4">
          <Card className="mx-auto max-w-7xl p-0">
            <WizardStepper experiment={experiment} />
          </Card>
        </div>
      ) : null}
    </div>
  )
}

export default Wizard
