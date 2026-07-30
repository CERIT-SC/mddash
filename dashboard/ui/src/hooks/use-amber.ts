import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { AmberJob } from "@/util/types"

export function useAmberStatuses(experimentId: string) {
  return useQuery<AmberJob[]>({
    queryKey: ["experiment", experimentId, "amber"],
    queryFn: () => api.get(`/experiments/${experimentId}/amber`).then((r) => r.data),
    enabled: !!experimentId,
  })
}

export function useAmberStatus(experimentId: string, simulationPath: string, enabled = true) {
  return useQuery<AmberJob>({
    queryKey: ["experiment", experimentId, "amber", simulationPath],
    queryFn: () => api.get(`/experiments/${experimentId}/amber/${simulationPath}`).then((r) => r.data),
    enabled: enabled && !!experimentId && !!simulationPath,
    meta: { suppressError: true },
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data || data.status === "FINISHED" || data.status === "ERROR") return false
      return 5000
    },
  })
}

interface SubmitAmberVariables {
  simulationPath: string
  binary: string
  ewald: string
  np: number
  ntomp: number
}

export function useSubmitAmber(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<AmberJob, Error, SubmitAmberVariables>({
    mutationFn: ({ simulationPath, ...params }) =>
      api.post(`/experiments/${experimentId}/amber/${simulationPath}`, params).then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "amber", job.simulation_path], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "amber"], exact: true })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteAmber(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (simulationPath) => {
      await api.delete(`/experiments/${experimentId}/amber/${simulationPath}`)
    },
    onSuccess: (_data, simulationPath) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "amber", simulationPath] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "amber"], exact: true })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useAmberLogs(
  experimentId: string,
  simulationPath: string,
  logType: "mdout" | "mdinfo" | "stdout" | "stderr" | "",
  shouldPoll: boolean,
  tail = 100
) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "amber", simulationPath, "logs", logType],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/amber/${simulationPath}/log`, { params: { type: logType, tail } })
        .then((r) => r.data),
    enabled: !!experimentId && !!simulationPath && !!logType,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}
