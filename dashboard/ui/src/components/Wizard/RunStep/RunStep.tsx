import type { ComponentType } from "react"

import { Engine } from "@/util/const"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

// AmberRunPanel will be created in Task 20
// @ts-expect-error AmberRunPanel will be created in Task 20
import AmberRunPanel from "./AmberRunPanel"
import GmxRunPanel from "./GmxRunPanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxRunPanel,
  [Engine.AMBER]: AmberRunPanel,
}

const RunStep = (props: WizardStepProps) => {
  const Panel = ENGINE_PANELS[props.experiment.engine]
  return <Panel {...props} />
}

export default RunStep
