import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { delete_gmx, gmx_logs, gmx_status, gmx_statuses, submit_gmx } from "@/util/api"
import type { GromacsJob } from "@/util/types"

export function useGromacsStatuses(experimentId: string) {
  return useQuery<GromacsJob[]>({
    queryKey: ["experiment", experimentId, "gmx"],
    queryFn: async () => {
      const { data, error } = await gmx_statuses(experimentId)
      if (error) throw new Error(error)
      return data ?? []
    },
    enabled: !!experimentId,
  })
}

export function useGromacsStatus(experimentId: string, tprName: string, shouldPoll: boolean) {
  return useQuery<GromacsJob>({
    queryKey: ["experiment", experimentId, "gmx", tprName],
    queryFn: async () => {
      const { data, error } = await gmx_status(experimentId, tprName)
      if (error) throw new Error(error)
      return data!
    },
    enabled: !!experimentId && !!tprName,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}

interface SubmitGmxVariables {
  tprName: string
  formData: FormData
}

export function useSubmitGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<GromacsJob, Error, SubmitGmxVariables>({
    mutationFn: async ({ tprName, formData }) => {
      const { data, error } = await submit_gmx(experimentId, tprName, formData)
      if (error) throw new Error(error)
      return data!
    },
    onSuccess: (job) => {
      queryClient.setQueryData(["experiment", experimentId, "gmx", job.tpr_name], job)
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "gmx"],
        exact: true,
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteGmx(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (tprName) => {
      const { error } = await delete_gmx(experimentId, tprName)
      if (error) throw new Error(error)
    },
    onSuccess: (_data, tprName) => {
      queryClient.removeQueries({
        queryKey: ["experiment", experimentId, "gmx", tprName],
      })
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "gmx"],
        exact: true,
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useGromacsLogs(
  experimentId: string,
  tprName: string,
  logType: "gmx" | "stdout" | "stderr",
  shouldPoll: boolean
) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "gmx", tprName, "logs", logType],
    queryFn: async () => {
      const { data, error } = await gmx_logs(experimentId, tprName, logType, 100)
      if (error) throw new Error(error)
      return "...\n" + (data ?? "")
    },
    enabled: !!experimentId && !!tprName,
    refetchInterval: shouldPoll ? 5000 : false,
  })
}
