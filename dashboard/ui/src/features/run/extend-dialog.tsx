import { useState } from "react"

import { parsePositiveInt } from "@/shared/parse"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Input,
  Label,
} from "@e-infra/design-system"
import { FastForward, LoaderCircle } from "lucide-react"

type ExtendDialogProps = {
  /** Current cumulative step total; shown in the resulting-total hint when known. */
  currentTotal: number | null
  pending: boolean
  onExtend: (nsteps: number) => void
  onCancel: () => void
}

/**
 * Extend a finished/stopped GMX run by additional steps. The server resumes from
 * the latest checkpoint and mdrun appends, so outputs and logs are never deleted.
 */
export function ExtendDialog({ currentTotal, pending, onExtend, onCancel }: ExtendDialogProps) {
  const [text, setText] = useState("")
  const parsed = parsePositiveInt(text)
  const valid = parsed !== null

  return (
    <AlertDialog
      open
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <FastForward className="text-primary" aria-hidden />
            Extend the run?
          </AlertDialogTitle>
          <AlertDialogDescription>
            The simulation continues from its latest checkpoint and appends to the existing results — nothing is
            deleted. The operation is recorded as a new segment in the run history.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-2">
          <Label htmlFor="extend-nsteps">Additional steps</Label>
          <Input
            id="extend-nsteps"
            type="number"
            min={1}
            value={text}
            autoFocus
            disabled={pending}
            placeholder="e.g. 100000"
            onChange={(event) => setText(event.target.value)}
          />
          {valid && currentTotal !== null && (
            <p className="text-text-muted text-sm tabular-nums">
              {`Extends the run from ${currentTotal.toLocaleString("en-US")} to ${(currentTotal + parsed).toLocaleString("en-US")} total steps.`}
            </p>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => (parsed === null ? undefined : onExtend(parsed))}
            disabled={!valid || pending}
          >
            {pending ? <LoaderCircle className="animate-spin" aria-hidden /> : <FastForward aria-hidden />}
            Extend
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
