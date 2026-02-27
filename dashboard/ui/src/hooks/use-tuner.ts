import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { TunerJob } from "@/util/types"

export function useTunerStatuses(experimentId: string) {
  return useQuery<TunerJob[]>({
    queryKey: ["experiment", experimentId, "tuner"],
    queryFn: () => api.get(`/experiments/${experimentId}/tuner`).then((r) => r.data),
    enabled: !!experimentId,
  })
}

export function useTunerStatus(experimentId: string, tprName: string) {
  return useQuery<TunerJob>({
    queryKey: ["experiment", experimentId, "tuner", tprName],
    queryFn: () => api.get(`/experiments/${experimentId}/tuner/${tprName}`).then((r) => r.data),
    enabled: !!experimentId && !!tprName,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data || data.error_message || data.tuner_status === "ERROR" || data.is_stopped || data.tuner_status === "TERMINATED") return false
      return 5000
    },
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
    mutationFn: ({ tprName, nsteps = 25000, extra_args = "" }) =>
      api
        .post(`/experiments/${experimentId}/tuner/${tprName}`, null, { params: { nsteps, extra_args } })
        .then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "tuner", job.tpr_name], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useStopTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      await api.post(`/experiments/${experimentId}/tuner/${tprName}/stop`)
    },
    onSuccess: (_data, tprName) => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner", tprName] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      await api.delete(`/experiments/${experimentId}/tuner/${tprName}`)
    },
    onSuccess: (_data, tprName) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "tuner", tprName] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
