import { useState } from "react"

import { toApiError } from "@/api/errors"
import { getGetExperimentQueryKey, getListSimulationsQueryKey, useDeleteSimulation } from "@/api/generated/client"
import type { Simulation } from "@/api/generated/models"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  buttonVariants,
  cn,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Ellipsis, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"

/** Tab value of the single unnamed create tab. Simulation.write rejects `_new` as a
    manifest name (409 reserved), so the URL can never collide with a real simulation. */
export const CREATE_TAB = "_new"

/* Browser-style tab boxes overriding the DS pill treatment (! — brittle on retune).
   Inactive tabs float on the canvas as bg-surface boxes; the active tab matches
   the wizard panel's bg-background so box and panel fuse into one. */
const TAB_BOX =
  "relative -ml-px h-9 flex-none items-center rounded-t-md rounded-b-none! border border-b-0 border-border! bg-surface px-3 text-text-muted! first:ml-0"
const FUSED_ACTIVE =
  "has-data-[state=active]:z-10 has-data-[state=active]:bg-background has-data-[state=active]:text-text"
/* The trigger inside a fused tab carries no styling of its own — the wrapper is the box. */
const INNER_TRIGGER =
  "h-auto! flex-none rounded-none! border-0! bg-transparent! px-0! py-0! text-inherit! data-[state=active]:bg-transparent! data-[state=active]:shadow-none dark:data-[state=active]:border-transparent dark:data-[state=active]:bg-transparent!"

type SimulationTabsProps = {
  experimentId: string
  simulations: Simulation[]
  /** Active tab — a simulation path, or CREATE_TAB. */
  value: string
  onValueChange: (value: string) => void
  /** Called with the deleted simulation so the wizard can fix up the URL. */
  onDeleted: (deleted: Simulation) => void
}

export function SimulationTabs({ experimentId, simulations, value, onValueChange, onDeleted }: SimulationTabsProps) {
  const queryClient = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<Simulation | null>(null)
  const creating = value === CREATE_TAB

  const remove = useDeleteSimulation({
    mutation: {
      onSuccess: (_response, { simulationPath }) => {
        const deleted = simulations.find((candidate) => candidate.simulation_path === simulationPath)
        toast.success(`Simulation “${deleted?.name ?? simulationPath}” deleted`)
        void queryClient.invalidateQueries({ queryKey: getListSimulationsQueryKey(experimentId) })
        // The experiment's latest_simulation_path may have pointed at the deleted manifest.
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
        if (deleted) onDeleted(deleted)
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  return (
    <>
      <div className="flex items-center gap-1">
        <Tabs value={value} onValueChange={onValueChange}>
          <TabsList
            aria-label="Simulations"
            className="relative z-10 -mb-px h-auto! w-full! flex-nowrap items-end! justify-start! gap-0 overflow-x-auto rounded-none! bg-transparent! p-0!"
          >
            {simulations.map((simulation) => (
              // The menu must not nest inside the trigger's <button role="tab"> (invalid
              // HTML); the fused styling makes name and menu read as one tab.
              <div key={simulation.simulation_path} className={cn(TAB_BOX, FUSED_ACTIVE, "flex gap-1 pr-1.5")}>
                <TabsTrigger value={simulation.simulation_path} className={INNER_TRIGGER}>
                  <span className="max-w-48 truncate">{simulation.name}</span>
                </TabsTrigger>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-text-muted size-6"
                      aria-label={`Actions for ${simulation.name}`}
                    >
                      <Ellipsis />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    {/* Renaming belongs to the Setup-step editor; delete is the only tab action. */}
                    <DropdownMenuItem variant="error" onSelect={() => setDeleteTarget(simulation)}>
                      <Trash2 className="h-4 w-4" /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))}
            {creating && (
              // Exists only while creating — naming it in Setup replaces it with a real tab.
              <div className={cn(TAB_BOX, FUSED_ACTIVE, "flex")}>
                <TabsTrigger value={CREATE_TAB} className={INNER_TRIGGER}>
                  [Unnamed Simulation]
                </TabsTrigger>
              </div>
            )}
          </TabsList>
        </Tabs>
        {/* DS buttons inherit font size; match the tab labels. */}
        <Button variant="link" size="sm" className="px-2! text-sm underline" onClick={() => onValueChange(CREATE_TAB)}>
          <Plus aria-hidden="true" /> New simulation
        </Button>
      </div>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="text-error h-5 w-5" aria-hidden="true" />
              Delete simulation “{deleteTarget?.name}”?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the simulation manifest and all related jobs. This can’t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {/* TODO: variant prop pending CERIT-SC/design-system#108 (see experiment-card) */}
            <AlertDialogAction
              className={buttonVariants({ variant: "error" })}
              onClick={() =>
                deleteTarget && remove.mutate({ experimentId, simulationPath: deleteTarget.simulation_path })
              }
              disabled={remove.isPending}
            >
              <Trash2 aria-hidden="true" />
              Delete simulation
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
