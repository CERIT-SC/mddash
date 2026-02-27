import { useEffect, useRef } from "react"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { edit_experiment, get_experiment, get_experiment_step } from "@/util/api"
import type { Experiment } from "@/util/types"

export function useExperiment(id: string) {
  return useQuery<Experiment>({
    queryKey: ["experiment", id],
    queryFn: async () => {
      const { data, error } = await get_experiment(id)
      if (error) throw new Error(error)
      return data!
    },
    enabled: !!id,
  })
}

export function useExperimentStep(id: string, currentStep: number) {
  const queryClient = useQueryClient()
  const prevStepRef = useRef(currentStep)

  const query = useQuery<number>({
    queryKey: ["experiment", id, "step"],
    queryFn: async () => {
      const { data, error } = await get_experiment_step(id)
      if (error) throw new Error(error)
      return data!
    },
    enabled: !!id,
    refetchInterval: 5000,
  })

  // When the step changes, update the experiment cache
  useEffect(() => {
    if (query.data !== undefined && query.data !== prevStepRef.current) {
      prevStepRef.current = query.data
      queryClient.setQueryData<Experiment>(["experiment", id], (old) => (old ? { ...old, step: query.data! } : old))
    }
  }, [query.data, id, queryClient])

  return query
}

export function useEditExperiment() {
  const queryClient = useQueryClient()

  return useMutation<Experiment, Error, { id: string; data: object }>({
    mutationFn: async ({ id, data }) => {
      const { data: result, error } = await edit_experiment(id, data)
      if (error) throw new Error(error)
      return result!
    },
    onSuccess: (updatedExperiment) => {
      queryClient.setQueryData(["experiment", updatedExperiment.id], updatedExperiment)
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
