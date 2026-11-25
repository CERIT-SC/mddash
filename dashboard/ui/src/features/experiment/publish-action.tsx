import type { Experiment, Simulation } from "@/api/generated/models"
import { PublishStep } from "@/features/publish"
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
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
    <>
      {reason === undefined ? (
        <Button type="button" onClick={() => onOpenChange(true)}>
          <Upload aria-hidden="true" />
          Publish
        </Button>
      ) : (
        <Tooltip>
          {/* A disabled button gets no pointer events, so the focusable wrapper carries the hover. */}
          <TooltipTrigger asChild>
            <span tabIndex={0} aria-label={`Publish: ${reason}`} className="inline-flex">
              <Button type="button" disabled>
                <Upload aria-hidden="true" />
                Publish
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
      )}
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
    </>
  )
}
