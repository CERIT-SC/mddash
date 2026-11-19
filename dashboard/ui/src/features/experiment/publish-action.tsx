import type { Experiment, Simulation } from "@/api/generated/models"
import { PublishStep } from "@/features/publish"
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Muted,
} from "@e-infra/design-system"
import { Upload } from "lucide-react"

type PublishActionProps = {
  experiment: Experiment
  simulation: Simulation | undefined
  /** Why Publish is unavailable; undefined once it can open. */
  reason: string | undefined
  /** URL-owned, so the MDRepo sign-in round trip lands back in the dialog. */
  open: boolean
  onOpenChange: (open: boolean) => void
  onOAuthHandled: () => void
}

/** Experiment-level Publish: a title-row button opening today's publish flow in a dialog. */
export function PublishAction({
  experiment,
  simulation,
  reason,
  open,
  onOpenChange,
  onOAuthHandled,
}: PublishActionProps) {
  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button type="button" disabled={reason !== undefined} onClick={() => onOpenChange(true)}>
        <Upload aria-hidden="true" />
        Publish…
      </Button>
      {reason !== undefined && <Muted className="max-w-72 sm:text-right">{reason}</Muted>}
      {simulation !== undefined && (
        <Dialog open={open && reason === undefined} onOpenChange={onOpenChange}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
            <DialogHeader>
              <DialogTitle>Publish your experiment</DialogTitle>
              <DialogDescription>
                Upload the experiment&apos;s data to a public repository to make it citable, or hand it off to MDPosit.
              </DialogDescription>
            </DialogHeader>
            <PublishStep
              experiment={experiment}
              simulation={simulation}
              onClose={() => onOpenChange(false)}
              onOAuthHandled={onOAuthHandled}
            />
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
