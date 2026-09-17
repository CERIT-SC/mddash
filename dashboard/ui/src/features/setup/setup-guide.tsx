import type { Notebook } from "@/api/generated/models"
import { NotebookLauncher } from "@/features/notebook"
import { StepGuide, type StepGuideState, type StepGuideStep } from "@/shared/ui/step-guide"
import { Button, Small } from "@e-infra/design-system"
import { ExternalLink } from "lucide-react"

type SetupGuideProps = {
  experimentId: string
  notebook: Notebook | undefined
  ready: boolean
  probeFailures: number
  openHref: string
  manifestExists: boolean
}

/** A manifest implies the pipeline already ran, so a stopped notebook never rewinds the guide. */
export function SetupGuide({
  experimentId,
  notebook,
  ready,
  probeFailures,
  openHref,
  manifestExists,
}: SetupGuideProps) {
  const step1: StepGuideState = ready || manifestExists ? "done" : "active"
  const step2: StepGuideState = manifestExists ? "done" : ready ? "active" : "pending"
  const step3: StepGuideState = manifestExists ? "active" : "pending"

  const steps: StepGuideStep[] = [
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

  return <StepGuide title="Step by step" label="Setup guide" steps={steps} />
}
