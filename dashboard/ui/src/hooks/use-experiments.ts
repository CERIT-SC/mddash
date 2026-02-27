import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { Experiment } from "@/util/types"

export function useExperiments() {
  return useQuery<Experiment[]>({
    queryKey: ["experiments"],
    queryFn: () => api.get("/experiments").then((r) => r.data),
  })
}

export function useDeleteExperiment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/experiments/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useCreateExperiment() {
  const queryClient = useQueryClient()

  return useMutation<Experiment, Error, FormData>({
    mutationFn: (formData) => api.post("/experiments", formData).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
