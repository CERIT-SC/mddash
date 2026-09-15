import type { ReactNode } from "react"

import { InfoBanner } from "@/shared/ui/info-banner"
import { cn } from "@e-infra/design-system"
import { Check } from "lucide-react"

export type StepGuideState = "done" | "active" | "pending"

export type StepGuideStep = {
  title: ReactNode
  state: StepGuideState
  body?: ReactNode
}

type StepGuideProps = {
  title: string
  /** Region aria-label naming the flow it guides (e.g. "Publish steps"). */
  label: string
  steps: StepGuideStep[]
  className?: string
}

/** Vertical numbered guide: a step is done once its outcome holds, the first unmet
 * one claims "active" (several may share it when they unlock together). */
export function StepGuide({ title, label, steps, className }: StepGuideProps) {
  return (
    <InfoBanner
      role="region"
      aria-label={label}
      className={cn("border-info-600 flex flex-col gap-3 border-l-8", className)}
    >
      <p className="font-medium tracking-tight">{title}</p>
      <ol className="space-y-4">
        {steps.map((step, index) => (
          <li key={index} className="relative flex gap-3">
            {index < steps.length - 1 && (
              <span className="bg-border absolute top-7 left-3.5 h-[calc(100%-1.75rem)] w-px" aria-hidden="true" />
            )}
            <StepMarker state={step.state} index={index} />
            <div className="min-w-0 flex-1 space-y-2 pt-0.5">
              <p
                className={cn(
                  "text-sm font-semibold",
                  step.state === "done" && "text-text-muted line-through",
                  step.state === "pending" && "text-text-muted"
                )}
              >
                {step.title}
              </p>
              {step.body}
            </div>
          </li>
        ))}
      </ol>
    </InfoBanner>
  )
}

function StepMarker({ state, index }: { state: StepGuideState; index: number }) {
  if (state === "done") {
    return (
      <span
        aria-label={`Step ${index + 1} done`}
        className="bg-success text-success-foreground flex size-7 shrink-0 items-center justify-center rounded-full"
      >
        <Check className="size-4" aria-hidden="true" />
      </span>
    )
  }
  return (
    <span
      aria-current={state === "active" ? "step" : undefined}
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        state === "active" ? "bg-primary text-primary-foreground" : "border-border text-text-muted border"
      )}
    >
      {index + 1}
    </span>
  )
}
