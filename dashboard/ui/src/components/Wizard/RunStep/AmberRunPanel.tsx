import { useAmberStatuses } from "@/hooks/use-amber"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberRunView from "./AmberRunView"

const AmberRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: amberJobs = [], refetch: refetchJobs } = useAmberStatuses(experiment.id)

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        {props.selectedSimulation && (
          <AmberRunView
            simulationPath={props.selectedSimulation.simulation_path}
            hasSimulationJob={amberJobs.some(
              (job) => job.simulation_path === props.selectedSimulation?.simulation_path
            )}
            onStartJob={refetchJobs}
            {...props}
          />
        )}
      </div>
    </div>
  )
}

export default AmberRunPanel
