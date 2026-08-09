import { useGromacsStatuses } from "@/hooks/use-gromacs"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import RunView from "./RunView"

const GmxRunPanel = (props: WizardStepProps) => {
  const { experiment } = props

  const { data: gromacsJobs = [], refetch: refetchJobs } = useGromacsStatuses(experiment.id)

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full flex-col gap-4">
        {props.simulation && (
          <RunView
            simulationPath={props.simulation.simulation_path}
            hasSimulationJob={gromacsJobs.some((job) => job.simulation_path === props.simulation?.simulation_path)}
            onStartJob={refetchJobs}
            {...props}
          />
        )}
      </div>
    </div>
  )
}

export default GmxRunPanel
