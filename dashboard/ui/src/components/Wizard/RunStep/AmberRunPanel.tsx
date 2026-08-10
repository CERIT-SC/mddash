import { useAmberStatuses } from "@/hooks/use-amber"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AmberRunView from "./AmberRunView"

const AmberRunPanel = ({ experiment, simulation, goToStep }: WizardStepProps) => {
  const { data: amberJobs = [], refetch: refetchJobs } = useAmberStatuses(experiment.id)

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        {simulation && (
          <AmberRunView
            experiment={experiment}
            simulation={simulation}
            goToStep={goToStep}
            simulationPath={simulation.simulation_path}
            hasSimulationJob={amberJobs.some((job) => job.simulation_path === simulation.simulation_path)}
            onStartJob={refetchJobs}
          />
        )}
      </div>
    </div>
  )
}

export default AmberRunPanel
