import { useGromacsStatuses } from "@/hooks/use-gromacs"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import RunView from "./RunView"

const GmxRunPanel = ({ experiment, simulation, goToStep }: WizardStepProps) => {
  const { data: gromacsJobs = [], refetch: refetchJobs } = useGromacsStatuses(experiment.id)

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        {simulation && (
          <RunView
            experiment={experiment}
            simulation={simulation}
            goToStep={goToStep}
            simulationPath={simulation.simulation_path}
            hasSimulationJob={gromacsJobs.some((job) => job.simulation_path === simulation.simulation_path)}
            onStartJob={refetchJobs}
          />
        )}
      </div>
    </div>
  )
}

export default GmxRunPanel
