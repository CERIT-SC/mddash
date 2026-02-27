import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { Notebook } from "@/util/types"

export function useNotebook(experimentId: string, refetchInterval: number | false = false) {
  return useQuery<Notebook>({
    queryKey: ["experiment", experimentId, "notebook"],
    queryFn: () => api.get(`/experiments/${experimentId}/notebook`).then((r) => r.data),
    enabled: !!experimentId,
    refetchInterval,
  })
}

export function useSpawnNotebook(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<Notebook, Error>({
    mutationFn: () => api.post(`/experiments/${experimentId}/notebook`).then((r) => r.data),
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
