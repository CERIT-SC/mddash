import { useEffect, useRef } from "react"

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

export function useExperimentStep(id: string, currentStep: number) {
  const queryClient = useQueryClient()
  const prevStepRef = useRef(currentStep)

  const query = useQuery<number>({
    queryKey: ["experiment", id, "step"],
    queryFn: () => api.get(`/experiments/${id}/step`).then((r) => r.data),
    enabled: !!id,
    refetchInterval: 5000,
  })

  // When the step changes, update the experiment cache and refetch simulations
  useEffect(() => {
    if (query.data !== undefined && query.data !== prevStepRef.current) {
      prevStepRef.current = query.data
      queryClient.setQueryData<Experiment>(["experiment", id], (old) => (old ? { ...old, step: query.data! } : old))
      queryClient.invalidateQueries({ queryKey: ["experiment", id, "simulations"] })
    }
  }, [query.data, id, queryClient])

  return query
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
