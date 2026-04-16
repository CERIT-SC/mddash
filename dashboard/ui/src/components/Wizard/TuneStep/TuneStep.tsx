import type { ComponentType } from "react"

import { Engine } from "@/util/const"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import GmxTunePanel from "./GmxTunePanel"
// AmberTunePanel will be created in Task 21
// @ts-expect-error AmberTunePanel will be created in Task 21
import AmberTunePanel from "./AmberTunePanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxTunePanel,
  [Engine.AMBER]: AmberTunePanel,
}

const TuneStep = (props: WizardStepProps) => {
  const Panel = ENGINE_PANELS[props.experiment.engine]
  return <Panel {...props} />
}

export default TuneStep