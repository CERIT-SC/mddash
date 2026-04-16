import { useState } from "react"

import type { FileOption } from "@/util/types"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberInputSelector from "../AmberInputSelector"
import AmberRunView from "./AmberRunView"

const AmberRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const [selectedPrmtop, setSelectedPrmtop] = useState<FileOption | null>(null)
  const [selectedInpcrd, setSelectedInpcrd] = useState<FileOption | null>(null)
  const [selectedMdin, setSelectedMdin] = useState<FileOption | null>(null)

  const allFilesSelected = selectedPrmtop && selectedInpcrd && selectedMdin

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row gap-4">
        <AmberInputSelector
          experimentId={experiment.id}
          onPrmtopSelected={setSelectedPrmtop}
          onInpcrdSelected={setSelectedInpcrd}
          onMdinSelected={setSelectedMdin}
        />

        {allFilesSelected && (
          <div className="flex-1">
            <AmberRunView
              prmtopName={selectedPrmtop.name}
              onStartJob={() => {}}
              {...props}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default AmberRunPanel