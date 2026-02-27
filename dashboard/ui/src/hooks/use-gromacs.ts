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

export function useGromacsStatus(experimentId: string, tprName: string) {
  return useQuery<GromacsJob>({
    queryKey: ["experiment", experimentId, "gmx", tprName],
    queryFn: () => api.get(`/experiments/${experimentId}/gmx/${tprName}`).then((r) => r.data),
    enabled: !!experimentId && !!tprName,
    meta: { suppressError: true },
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data || data.status === "TERMINATED" || data.status === "ERROR") return false
      return 5000
    },
  })
}

interface SubmitGmxVariables {
  tprName: string
  formData: FormData
}

export function useSubmitGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<GromacsJob, Error, SubmitGmxVariables>({
    mutationFn: ({ tprName, formData }) =>
      api.post(`/experiments/${experimentId}/gmx/${tprName}`, formData).then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "gmx", job.tpr_name], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "gmx"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      await api.delete(`/experiments/${experimentId}/gmx/${tprName}`)
    },
    onSuccess: (_data, tprName) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "gmx", tprName] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "gmx"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useGromacsLogs(
  experimentId: string,
  tprName: string,
  logType: "gmx" | "stdout" | "stderr" | "",
  shouldPoll: boolean,
  tail = 100
) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "gmx", tprName, "logs", logType],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/gmx/${tprName}/log`, { params: { type: logType, tail } })
        .then((r) => "...\n" + r.data),
    enabled: !!experimentId && !!tprName && !!logType,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}
