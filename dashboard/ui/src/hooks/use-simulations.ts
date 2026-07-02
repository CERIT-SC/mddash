import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { Simulation } from "@/util/types"

export function useSimulations(experimentId: string) {
  return useQuery<Simulation[]>({
    queryKey: ["experiment", experimentId, "simulations"],
    queryFn: () => api.get(`/experiments/${experimentId}/simulations`).then((r) => r.data),
    enabled: !!experimentId,
  })
}

export function useSimulation(experimentId: string, simulationPath: string | null) {
  return useQuery<Simulation>({
    queryKey: ["experiment", experimentId, "simulations", simulationPath],
    queryFn: () => api.get(`/experiments/${experimentId}/simulations/${simulationPath}`).then((r) => r.data),
    enabled: !!experimentId && !!simulationPath,
    meta: { suppressError: true },
  })
}

export interface SimulationPayload {
  name: string
  files: Record<string, string>
  extra_args: string
  simulation_path?: string
}

export function useCreateSimulation(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<Simulation, Error, SimulationPayload>({
    mutationFn: (payload) => api.post(`/experiments/${experimentId}/simulations`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId] })
      toast.success("Simulation created")
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useUpdateSimulation(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<Simulation, Error, { simulationPath: string; payload: SimulationPayload }>({
    mutationFn: ({ simulationPath, payload }) =>
      api.patch(`/experiments/${experimentId}/simulations/${simulationPath}`, payload).then((r) => r.data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "simulations"] })
      queryClient.invalidateQueries({
        queryKey: ["experiment", experimentId, "simulations", variables.simulationPath],
      })
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId] })
      toast.success("Simulation updated")
    },
    onError: (error: Error) => toast.error(error.message),
  })
}
