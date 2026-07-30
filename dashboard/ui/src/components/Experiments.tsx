import { useState } from "react"

import { Link } from "@tanstack/react-router"
import { Loader2, PlusCircle, Trash2, Wand2 } from "lucide-react"

import type { Experiment } from "@/util/types"
import { useDeleteExperiment, useExperiments } from "@/hooks/use-experiments"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter } from "@/components/ui/card"
import { PodStatusChip } from "@/components/PodStatusChip"

import ConfirmDialog from "./ConfirmDialog"

const Experiments = () => {
  const { data: experiments = [], isLoading } = useExperiments()
  const deleteExperiment = useDeleteExperiment()

  const [experimentToDelete, setExperimentToDelete] = useState<Experiment | null>(null)
  const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false)

  const handleDeleteClick = (experiment: Experiment) => {
    setExperimentToDelete(experiment)
    setConfirmDeleteDialog(true)
  }

  const handleConfirmDelete = () => {
    if (experimentToDelete) {
      deleteExperiment.mutate(experimentToDelete.id)
      setExperimentToDelete(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-48 items-center justify-center">
        <Loader2 className="text-muted-foreground h-10 w-10 animate-spin" />
      </div>
    )
  }

  return (
    <div className="px-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {experiments.map((experiment) => {
          const notebookStatus = experiment.notebook?.status || "UNKNOWN"
          return (
            <Card key={experiment.id} className="flex flex-col justify-between">
              <CardContent className="flex flex-col gap-1 pt-4">
                <h3 className="text-base font-semibold">{experiment.name}</h3>
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-muted-foreground font-medium">Step:</span>
                  <span>{experiment.step}</span>
                </div>
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-muted-foreground font-medium">Status:</span>
                  <span>{experiment.status}</span>
                </div>
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-muted-foreground font-medium">Notebook:</span>
                  <PodStatusChip status={notebookStatus} />
                </div>
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-muted-foreground font-medium">Tuner jobs:</span>
                  <span>{experiment.tuner_jobs.length}</span>
                </div>
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-muted-foreground font-medium">Simulation jobs:</span>
                  <span>{experiment.simulation_jobs.length}</span>
                </div>
              </CardContent>
              <CardFooter className="flex justify-center gap-2 pt-0">
                <Button size="sm" asChild>
                  <Link to="/$id/wizard" params={{ id: experiment.id }}>
                    <Wand2 className="mr-1 h-4 w-4" />
                    Wizard
                  </Link>
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
                  onClick={() => handleDeleteClick(experiment)}
                >
                  <Trash2 className="mr-1 h-4 w-4" />
                  Delete
                </Button>
              </CardFooter>
            </Card>
          )
        })}

        {/* New experiment card */}
        <Link to="/new" className="no-underline">
          <Card className="text-muted-foreground hover:border-primary hover:text-primary flex h-full min-h-40 cursor-pointer flex-col items-center justify-center border-2 border-dashed transition-colors">
            <CardContent className="flex flex-col items-center gap-2 py-6">
              <PlusCircle className="h-16 w-16" />
              <span className="text-lg font-medium">New</span>
            </CardContent>
          </Card>
        </Link>
      </div>

      <ConfirmDialog
        open={confirmDeleteDialog}
        setOpen={setConfirmDeleteDialog}
        onConfirm={handleConfirmDelete}
        message="Are you sure you want to delete this experiment? All data will be lost."
      />
    </div>
  )
}

export default Experiments
