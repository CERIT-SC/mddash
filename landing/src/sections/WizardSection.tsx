import { useState } from "react"

import { Card, CardContent, CardHeader, CardTitle, H2, Muted, P } from "@e-infra/design-system"
import { ChevronRight } from "lucide-react"

import analyzeDarkImg from "../assets/analyze-dark.png"
import analyzeLightImg from "../assets/analyze-light.png"
import publishDarkImg from "../assets/publish-dark.png"
import publishLightImg from "../assets/publish-light.png"
import runDarkImg from "../assets/run-dark.png"
import runLightImg from "../assets/run-light.png"
import setupImg from "../assets/setup.png"
import tuneDarkImg from "../assets/tune-dark.png"
import tuneLightImg from "../assets/tune-light.png"
import { useReveal } from "../hooks/useReveal"

type WizardStep = {
  num: number
  label: string
  tagline: string
  description: string
  lightImg: string
  darkImg: string
  alt: string
  width: number
  height: number
}

const WIZARD_STEPS: WizardStep[] = [
  {
    num: 1,
    label: "Setup",
    tagline: "Reproducible from the first command",
    description:
      "Jupyter notebooks replace ad hoc shell scripts. Notebooks are version-controlled, shareable, and self-documenting. Compatible with BioExcel Building Blocks (BioBB) via Binder. Experiments can be initialized from a PDB structure, a local upload, or any previously published MDRepo record.",
    lightImg: setupImg,
    darkImg: setupImg,
    alt: "MDDash setup step",
    width: 1612,
    height: 1462,
  },
  {
    num: 2,
    label: "Tune",
    tagline: "Optimal performance, automatically",
    description:
      "Integrated Tuner runs short GROMACS and AMBER benchmarks across MPI, OpenMP, and GPU configurations in parallel. The best-performing configuration is offered automatically — no manual guesswork, no wasted compute on long production runs.",
    lightImg: tuneLightImg,
    darkImg: tuneDarkImg,
    alt: "MDDash tune step with benchmark results",
    width: 1900,
    height: 1600,
  },
  {
    num: 3,
    label: "Run",
    tagline: "Live progress without shell access",
    description:
      "Kubernetes Jobs manage execution with proper resource allocation. Watch live progress, stream logs, and inspect intermediate files — all without needing shell access to the cluster. Jobs survive browser disconnects and pod restarts.",
    lightImg: runLightImg,
    darkImg: runDarkImg,
    alt: "MDDash run step with live progress",
    width: 1900,
    height: 1475,
  },
  {
    num: 4,
    label: "Analyze",
    tagline: "Three tools, one interface",
    description:
      "Mol* viewer embedded for 3D structures and trajectories. Full MDDB Workflow analyses with interactive charts. On-demand Jupyter notebooks for custom analysis with the complete Python scientific stack. Available during active runs for early issue detection.",
    lightImg: analyzeLightImg,
    darkImg: analyzeDarkImg,
    alt: "MDDash analysis step with charts",
    width: 1900,
    height: 2000,
  },
  {
    num: 5,
    label: "Publish",
    tagline: "One-click FAIR data publication",
    description:
      "One-click publication to MDRepo. Metadata auto-extracted with GROMACS MetaDump. Files upload in the background. The experiment receives a persistent DOI. Built on InvenioRDM — the same framework as Zenodo — enforcing MD-specific metadata schemas and standardized trajectory formats.",
    lightImg: publishLightImg,
    darkImg: publishDarkImg,
    alt: "MDDash publish step",
    width: 1900,
    height: 975,
  },
]

export function WizardSection() {
  const [active, setActive] = useState(0)
  const titleRef = useReveal()
  const activeStep = WIZARD_STEPS[active]

  return (
    <section className="bg-background py-24">
      <div className="container mx-auto max-w-7xl px-6">
        <div ref={titleRef} className="reveal mb-16 text-center">
          <Muted className="mb-3 text-sm font-semibold tracking-widest uppercase">The workflow</Muted>
          <H2 className="font-display text-text-heading mb-4 text-3xl lg:text-4xl">Five stages. One platform.</H2>
          <P className="text-text-muted mx-auto max-w-2xl">
            A wizard-driven interface guides researchers through every step of the simulation lifecycle, keeping
            metadata and provenance intact at each transition.
          </P>
        </div>

        <div className="grid items-start gap-8 lg:grid-cols-[320px_1fr]">
          <div className="flex flex-col gap-1" role="tablist" aria-label="Workflow steps">
            {WIZARD_STEPS.map((step, i) => (
              <button
                key={step.num}
                role="tab"
                aria-selected={active === i}
                onClick={() => setActive(i)}
                className={`step-tab rounded-lg px-5 py-4 text-left ${active === i ? "active" : ""}`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`font-display text-2xl font-light ${active === i ? "text-primary" : "text-text-muted"}`}
                  >
                    {step.num}
                  </span>
                  <div>
                    <div className={`text-sm font-semibold ${active === i ? "text-text" : "text-text-muted"}`}>
                      {step.label}
                    </div>
                    <div className="text-text-muted mt-0.5 text-xs">{step.tagline}</div>
                  </div>
                  {active === i && <ChevronRight size={14} className="text-primary ml-auto shrink-0" />}
                </div>
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-5">
            <div className="screen-frame overflow-hidden">
              <div className="bg-surface border-border/50 flex items-center gap-2 border-b px-4 py-2.5">
                <div className="flex gap-1.5">
                  <span className="bg-error h-2.5 w-2.5 rounded-full opacity-70" />
                  <span className="bg-warning h-2.5 w-2.5 rounded-full opacity-70" />
                  <span className="bg-success h-2.5 w-2.5 rounded-full opacity-70" />
                </div>
                <div className="ml-3 flex gap-1">
                  {WIZARD_STEPS.map((step, i) => (
                    <span
                      key={step.num}
                      className={`rounded-t-sm border-x border-t px-3 py-0.5 text-xs ${
                        i === active
                          ? "bg-surface border-border text-text"
                          : "text-text-muted border-transparent bg-transparent"
                      }`}
                    >
                      {step.label}
                    </span>
                  ))}
                </div>
              </div>
              {/* The Setup screenshot is a terminal window with no light/dark UI variants. */}
              <img
                src={activeStep.lightImg}
                alt={activeStep.alt}
                className={activeStep.darkImg === activeStep.lightImg ? "block w-full" : "block w-full dark:hidden"}
                width={activeStep.width}
                height={activeStep.height}
                key={`light-${active}`}
              />
              {activeStep.darkImg !== activeStep.lightImg && (
                <img
                  src={activeStep.darkImg}
                  alt={activeStep.alt}
                  className="hidden w-full dark:block"
                  width={activeStep.width}
                  height={activeStep.height}
                  key={`dark-${active}`}
                />
              )}
            </div>

            <Card className="gap-2">
              <CardHeader>
                <CardTitle className="text-base">
                  Step {activeStep.num}: {activeStep.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <P className="text-text-muted text-sm leading-relaxed">{activeStep.description}</P>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </section>
  )
}
