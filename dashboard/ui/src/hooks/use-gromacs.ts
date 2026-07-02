import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { GromacsJob } from "@/util/types"

export function useGromacsStatuses(experimentId: string) {
  return useQuery<GromacsJob[]>({
    queryKey: ["experiment", experimentId, "gmx"],
    queryFn: () => api.get(`/experiments/${experimentId}/gmx`).then((r) => r.data),
    enabled: !!experimentId,
  })
}

export function useGromacsStatus(experimentId: string, simulationPath: string) {
  return useQuery<GromacsJob>({
    queryKey: ["experiment", experimentId, "gmx", simulationPath],
    queryFn: () => api.get(`/experiments/${experimentId}/gmx/${simulationPath}`).then((r) => r.data),
    enabled: !!experimentId && !!simulationPath,
    meta: { suppressError: true },
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data || data.status === "TERMINATED" || data.status === "ERROR") return false
      return 5000
    },
  })
}

interface SubmitGmxVariables {
  simulationPath: string
  np: number
  ntomp: number
  pme: string
  nb: string
}

export function useSubmitGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<GromacsJob, Error, SubmitGmxVariables>({
    mutationFn: ({ simulationPath, ...params }) =>
      api.post(`/experiments/${experimentId}/gmx/${simulationPath}`, params).then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "gmx", job.simulation_path], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "gmx"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (simulationPath) => {
      await api.delete(`/experiments/${experimentId}/gmx/${simulationPath}`)
    },
    onSuccess: (_data, simulationPath) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "gmx", simulationPath] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "gmx"], exact: true })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useGromacsLogs(
  experimentId: string,
  simulationPath: string,
  logType: "gmx" | "stdout" | "stderr" | "",
  shouldPoll: boolean,
  tail = 100
) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "gmx", simulationPath, "logs", logType],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/gmx/${simulationPath}/log`, { params: { type: logType, tail } })
        .then((r) => "...\n" + r.data),
    enabled: !!experimentId && !!simulationPath && !!logType,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}
