import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { Notebook, NotebookConfig, NotebookTier } from "@/util/types"

export function useNotebook(experimentId: string, refetchInterval: number | false = false) {
  return useQuery<Notebook>({
    queryKey: ["experiment", experimentId, "notebook"],
    queryFn: () => api.get(`/experiments/${experimentId}/notebook`).then((r) => r.data),
    enabled: !!experimentId,
    refetchInterval,
  })
}

export function useNotebookConfig() {
  return useQuery<NotebookConfig>({
    queryKey: ["notebook-config"],
    queryFn: () => api.get("/notebook-config").then((r) => r.data),
    staleTime: Infinity,
  })
}

type SpawnParams = { tier?: NotebookTier; gpu?: boolean }

export function useSpawnNotebook(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<Notebook, Error, SpawnParams>({
    mutationFn: (params: SpawnParams = {}) =>
      api.post(`/experiments/${experimentId}/notebook`, params).then((r) => r.data),
    onSuccess: (notebook) => {
      queryClient.setQueryData(["experiment", experimentId, "notebook"], notebook)
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useStopNotebook(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error>({
    mutationFn: async () => {
      await api.delete(`/experiments/${experimentId}/notebook`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "notebook"],
      })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
