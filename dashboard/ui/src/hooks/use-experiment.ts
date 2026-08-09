import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { Experiment } from "@/util/types"

export function useExperiment(id: string) {
  return useQuery<Experiment>({
    queryKey: ["experiment", id],
    queryFn: () => api.get(`/experiments/${id}`).then((r) => r.data),
    enabled: !!id,
  })
}

export function useEditExperiment() {
  const queryClient = useQueryClient()

  return useMutation<Experiment, Error, { id: string; data: object }>({
    mutationFn: ({ id, data }) => api.patch(`/experiments/${id}`, data).then((r) => r.data),
    onSuccess: (updatedExperiment) => {
      queryClient.setQueryData(["experiment", updatedExperiment.id], updatedExperiment)
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
