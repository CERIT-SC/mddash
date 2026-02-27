import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { delete_tuner, run_tuner, stop_tuner, tuner_status, tuner_statuses } from "@/util/api"
import type { TunerJob } from "@/util/types"

export function useTunerStatuses(experimentId: string) {
  return useQuery<TunerJob[]>({
    queryKey: ["experiment", experimentId, "tuner"],
    queryFn: async () => {
      const { data, error } = await tuner_statuses(experimentId)
      if (error) throw new Error(error)
      return data ?? []
    },
    enabled: !!experimentId,
  })
}

export function useTunerStatus(experimentId: string, tprName: string, shouldPoll: boolean) {
  return useQuery<TunerJob>({
    queryKey: ["experiment", experimentId, "tuner", tprName],
    queryFn: async () => {
      const { data, error } = await tuner_status(experimentId, tprName)
      if (error) throw new Error(error)
      return data!
    },
    enabled: !!experimentId && !!tprName,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}

interface RunTunerVariables {
  tprName: string
  nsteps?: number
  extra_args?: string
}

export function useRunTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<TunerJob, Error, RunTunerVariables>({
    mutationFn: async ({ tprName, nsteps, extra_args }) => {
      const { data, error } = await run_tuner(experimentId, tprName, nsteps, extra_args)
      if (error) throw new Error(error)
      return data!
    },
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "tuner", job.tpr_name], job)
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "tuner"],
        exact: true,
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useStopTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      const { error } = await stop_tuner(experimentId, tprName)
      if (error) throw new Error(error)
    },
    onSuccess: (_data, tprName) => {
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "tuner", tprName],
      })
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "tuner"],
        exact: true,
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      const { error } = await delete_tuner(experimentId, tprName)
      if (error) throw new Error(error)
    },
    onSuccess: (_data, tprName) => {
      queryClient.removeQueries({
        queryKey: ["experiment", experimentId, "tuner", tprName],
      })
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "tuner"],
        exact: true,
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
