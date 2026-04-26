import type { ComponentType } from "react"

import { Engine } from "@/util/const"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberTunePanel from "./AmberTunePanel"
import GmxTunePanel from "./GmxTunePanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxTunePanel,
  [Engine.AMBER]: AmberTunePanel,
}

const TuneStep = (props: WizardStepProps) => {
  const Panel = ENGINE_PANELS[props.experiment.engine]
  return <Panel {...props} />
}

export default TuneStep
