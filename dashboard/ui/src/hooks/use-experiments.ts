import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { create_experiment, delete_experiment, get_experiments } from "@/util/api"
import type { Experiment } from "@/util/types"

export function useExperiments() {
  return useQuery<Experiment[]>({
    queryKey: ["experiments"],
    queryFn: async () => {
      const { data, error } = await get_experiments()
      if (error) throw new Error(error)
      return data ?? []
    },
  })
}

export function useDeleteExperiment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await delete_experiment(id)
      if (error) throw new Error(error)
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
    mutationFn: async (formData) => {
      const { data, error } = await create_experiment(formData)
      if (error) throw new Error(error)
      return data!
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
