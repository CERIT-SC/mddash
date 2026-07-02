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

export function useTunerStatus(experimentId: string, simulationPath: string) {
  return useQuery<TunerJob>({
    queryKey: ["experiment", experimentId, "tuner", simulationPath],
    queryFn: () => api.get(`/experiments/${experimentId}/tuner/${simulationPath}`).then((r) => r.data),
    enabled: !!experimentId && !!simulationPath,
    meta: { suppressError: true },
    refetchInterval: (query) => {
      const data = query.state.data
      if (
        !data ||
        data.error_message ||
        data.tuner_status === "ERROR" ||
        data.is_stopped ||
        data.tuner_status === "TERMINATED"
      )
        return false
      return 5000
    },
  })
}

interface RunTunerVariables {
  simulationPath: string
  nsteps?: number
}

export function useRunTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<TunerJob, Error, RunTunerVariables>({
    mutationFn: ({ simulationPath, nsteps = 25000 }) =>
      api.post(`/experiments/${experimentId}/tuner`, { simulation_path: simulationPath, nsteps }).then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "tuner", job.simulation_path], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useStopTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (simulationPath) => {
      await api.post(`/experiments/${experimentId}/tuner/${simulationPath}/stop`)
    },
    onSuccess: (_data, simulationPath) => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner", simulationPath] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useTunerTrialLogs(experimentId: string, simulationPath: string, trialId: string | null) {
  const enabled = !!experimentId && !!simulationPath && !!trialId

  const stdout = useQuery<string>({
    queryKey: ["experiment", experimentId, "tuner", simulationPath, "trials", trialId, "stdout"],
    queryFn: () =>
      api.get(`/experiments/${experimentId}/tuner/${simulationPath}/trials/${trialId}/stdout`).then((r) => r.data),
    enabled,
  })

  const stderr = useQuery<string>({
    queryKey: ["experiment", experimentId, "tuner", simulationPath, "trials", trialId, "stderr"],
    queryFn: () =>
      api.get(`/experiments/${experimentId}/tuner/${simulationPath}/trials/${trialId}/stderr`).then((r) => r.data),
    enabled,
  })

  return { stdout, stderr }
}

export function useDeleteTuner(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (simulationPath) => {
      await api.delete(`/experiments/${experimentId}/tuner/${simulationPath}`)
    },
    onSuccess: (_data, simulationPath) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "tuner", simulationPath] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "tuner"], exact: true })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
