import type { ComponentType } from "react"

import { Engine } from "@/util/const"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberTunePanel from "./AmberTunePanel"
import GmxTunePanel from "./GmxTunePanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxTunePanel,
  [Engine.AMBER]: AmberTunePanel,
}

const TuneStep = ({ experiment, simulation, goToStep }: WizardStepProps) => {
  const Panel = ENGINE_PANELS[experiment.engine]
  return <Panel experiment={experiment} simulation={simulation} goToStep={goToStep} />
}

export default TuneStep
