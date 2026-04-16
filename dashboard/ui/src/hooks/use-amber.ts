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

export function useAmberStatus(experimentId: string, prmtopName: string) {
  return useQuery<AmberJob>({
    queryKey: ["experiment", experimentId, "amber", prmtopName],
    queryFn: () => api.get(`/experiments/${experimentId}/amber/${prmtopName}`).then((r) => r.data),
    enabled: !!experimentId && !!prmtopName,
    meta: { suppressError: true },
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data || data.status === "TERMINATED" || data.status === "ERROR") return false
      return 5000
    },
  })
}

interface SubmitAmberVariables {
  prmtopName: string
  formData: FormData
}

export function useSubmitAmber(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<AmberJob, Error, SubmitAmberVariables>({
    mutationFn: ({ prmtopName, formData }) =>
      api.post(`/experiments/${experimentId}/amber/${prmtopName}`, formData).then((r) => r.data),
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "amber", job.prmtop_name], job)
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "amber"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteAmber(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (prmtopName) => {
      await api.delete(`/experiments/${experimentId}/amber/${prmtopName}`)
    },
    onSuccess: (_data, prmtopName) => {
      queryClient.removeQueries({ queryKey: ["experiment", experimentId, "amber", prmtopName] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "amber"], exact: true })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useAmberLogs(
  experimentId: string,
  prmtopName: string,
  logType: "stdout" | "stderr" | "",
  shouldPoll: boolean,
  tail = 100
) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "amber", prmtopName, "logs", logType],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/amber/${prmtopName}/log`, { params: { type: logType, tail } })
        .then((r) => "...\n" + r.data),
    enabled: !!experimentId && !!prmtopName && !!logType,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}
