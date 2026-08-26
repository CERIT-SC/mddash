import type { Notebook } from "@/api/generated/models"
import { NotebookLauncher } from "@/features/notebook"
import { Button, cn, Small } from "@e-infra/design-system"
import { Check, ExternalLink } from "lucide-react"

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
            <Small>This gives you a running environment to prepare the files.</Small>
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
            <Small>Wait for the run to finish.</Small>
          </>
        ) : null,
    },
    {
      title: "Go to Tune",
      state: step3,
      body: step3 === "active" ? <Small>Check the validity of data below and move on to tune.</Small> : null,
    },
  ]

  return (
    <section
      aria-label="Setup guide"
      className="border-info bg-info/50 supports-backdrop-filter:bg-info/60 space-y-3 rounded-lg border px-4 py-3 text-sm"
    >
      <p className="font-medium tracking-tight">Step by step</p>
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
