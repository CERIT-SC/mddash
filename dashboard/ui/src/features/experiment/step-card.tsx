import { useState, type ReactNode } from "react"

import { Button, cn, Collapsible, CollapsibleContent, CollapsibleTrigger, H4 } from "@e-infra/design-system"
import { Check, Lock } from "lucide-react"

/**
 * done: finished; current: being worked on; open: reachable while an earlier
 * step is still current (a live run whose frames already open Analysis);
 * locked: not reachable yet.
 */
export type StepCardState = "done" | "current" | "open" | "locked"

type StepCardProps = {
  id: string
  position: number
  title: string
  state: StepCardState
  /** One line beside the title: a done card's outcome or a locked card's reason. */
  note?: ReactNode
  /** Done cards whose content only matters for review fold it behind a toggle. */
  foldWhenDone?: boolean
  children?: ReactNode
}

export function StepCard({ id, position, title, state, note, foldWhenDone = false, children }: StepCardProps) {
  const [unfolded, setUnfolded] = useState(false)
  const titleId = `${id}-title`
  const folds = foldWhenDone && state === "done"

  return (
    <li id={id} aria-current={state === "current" ? "step" : undefined}>
      <Collapsible asChild open={!folds || unfolded} onOpenChange={setUnfolded}>
        <section
          aria-labelledby={titleId}
          className={cn("border-border rounded-lg border p-4 md:p-6", state === "locked" && "border-dashed")}
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span
              aria-hidden="true"
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                state === "done" && "bg-success text-success-foreground",
                state === "current" && "bg-primary text-primary-foreground",
                (state === "open" || state === "locked") && "border-border text-text-muted border"
              )}
            >
              {state === "done" ? <Check size={14} /> : position}
            </span>
            <H4 id={titleId} className={cn("text-lg", state === "locked" && "text-text-muted")}>
              {title}
            </H4>
            {note !== undefined && (
              <span className="text-text-muted flex items-center gap-1.5 text-sm">
                {state === "locked" && <Lock size={14} aria-hidden="true" className="shrink-0" />}
                {note}
              </span>
            )}
            {folds && (
              <CollapsibleTrigger asChild>
                <Button
                  variant="link"
                  size="sm"
                  className="ml-auto"
                  aria-label={`${unfolded ? "Hide" : "Show"} ${title}`}
                >
                  {unfolded ? "Hide" : "Show"}
                </Button>
              </CollapsibleTrigger>
            )}
          </div>
          {state !== "locked" && <CollapsibleContent className="mt-4 md:mt-6">{children}</CollapsibleContent>}
        </section>
      </Collapsible>
    </li>
  )
}
