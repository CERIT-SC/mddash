import type { Notebook } from "@/api/generated/models"
import { Button, cn } from "@e-infra/design-system"
import { Check, ExternalLink } from "lucide-react"

import { NotebookLauncher } from "./notebook-launcher"

type GuideState = "done" | "active" | "pending"

type SetupGuideProps = {
  experimentId: string
  notebook: Notebook | undefined
  ready: boolean
  probeFailures: number
  openHref: string
  manifestExists: boolean
}

/** A step is done as soon as its outcome holds; the first unmet one claims "active". */
export function SetupGuide({
  experimentId,
  notebook,
  ready,
  probeFailures,
  openHref,
  manifestExists,
}: SetupGuideProps) {
  const step1: GuideState = ready ? "done" : "active"
  const step2: GuideState = manifestExists ? "done" : ready ? "active" : "pending"
  const step3: GuideState = ready && manifestExists ? "active" : "pending"

  const steps: { title: React.ReactNode; body: React.ReactNode; state: GuideState }[] = [
    {
      title: "Start the notebook",
      state: step1,
      body:
        step1 === "active" ? (
          <>
            <p className="text-text-muted text-sm">This gives you a running environment to prepare the files.</p>
            <NotebookLauncher
              experimentId={experimentId}
              notebook={notebook}
              ready={ready}
              probeFailures={probeFailures}
              openHref={openHref}
            />
          </>
        ) : null,
    },
    {
      title: (
        <>
          <q>▶ Run Pipeline</q> in the notebook
        </>
      ),
      state: step2,
      body:
        step2 === "active" ? (
          <>
            <div>
              <Button size="sm" asChild>
                <a href={openHref} target="_blank" rel="noopener noreferrer" className="no-underline">
                  <ExternalLink aria-hidden="true" />
                  Open notebook
                </a>
              </Button>
            </div>
            <p className="text-text-muted text-sm">Wait for the run to finish.</p>
          </>
        ) : null,
    },
    {
      title: "Go to Tune",
      state: step3,
      body:
        step3 === "active" ? (
          <p className="text-text-muted text-sm">Check the validity of data below and move on to tune.</p>
        ) : null,
    },
  ]

  return (
    <section
      aria-label="Setup guide"
      className="border-info-300 bg-info-50 space-y-4 rounded-lg border border-l-4 p-4 md:p-6"
    >
      <p className="text-info text-xs font-semibold tracking-widest uppercase">Step by step</p>
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
    </section>
  )
}

function StepMarker({ state, index }: { state: GuideState; index: number }) {
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
