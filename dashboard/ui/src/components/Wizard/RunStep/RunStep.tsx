import type { ComponentType } from "react"

import { Engine } from "@/util/const"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberRunPanel from "./AmberRunPanel"
import GmxRunPanel from "./GmxRunPanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxRunPanel,
  [Engine.AMBER]: AmberRunPanel,
}

const RunStep = ({ experiment, simulation, goToStep }: WizardStepProps) => {
  const Panel = ENGINE_PANELS[experiment.engine]
  return <Panel experiment={experiment} simulation={simulation} goToStep={goToStep} />
}

export default RunStep
