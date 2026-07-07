import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { AnalysisJob, AnalysisPreprocessingMode } from "@/util/analysis-types"

export function useAnalysisJobs(experimentId: string, simulationPath: string | null) {
  return useQuery<AnalysisJob[]>({
    queryKey: ["experiment", experimentId, "analysis", simulationPath],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/analysis`, { params: { simulation_path: simulationPath } })
        .then((r) => r.data),
    enabled: !!experimentId && !!simulationPath,
    refetchInterval: (query) => {
      const jobs = query.state.data
      if (!jobs?.length) return false
      const hasActive = jobs.some((j) => j.status === "RUNNING" || j.status === "PENDING")
      return hasActive ? 5000 : false
    },
  })
}

interface SubmitAnalysisVariables {
  analysis: string
  simulation_path: string
  preprocessing_mode: AnalysisPreprocessingMode
}

export function useSubmitAnalysis(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<AnalysisJob, Error, SubmitAnalysisVariables>({
    mutationFn: (data) => api.post(`/experiments/${experimentId}/analysis`, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "analysis"] })
      toast.success("Analysis job submitted")
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useDeleteAnalysis(experimentId: string) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: async (jobId) => {
      await api.delete(`/experiments/${experimentId}/analysis/${jobId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "analysis"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useAnalysisData(experimentId: string, simulationPath: string, analysisName: string | null) {
  return useQuery<unknown>({
    queryKey: ["experiment", experimentId, "analysis-results", simulationPath, analysisName],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/analysis/results/${analysisName}`, {
          params: { simulation_path: simulationPath },
        })
        .then((r) => r.data),
    enabled: !!experimentId && !!simulationPath && !!analysisName,
  })
}

export interface AnalysisVariant {
  name: string
  analysis: string
}

export function useAnalysisLogs(experimentId: string, jobId: string | null, polling = false) {
  return useQuery<string>({
    queryKey: ["experiment", experimentId, "analysis-logs", jobId],
    queryFn: () => api.get(`/experiments/${experimentId}/analysis/${jobId}/logs`).then((r) => r.data),
    enabled: !!experimentId && !!jobId,
    refetchInterval: polling ? 5000 : false,
    staleTime: polling ? 0 : Infinity,
  })
}

export function useAvailableAnalysisResults(experimentId: string, simulationPath: string | null) {
  return useQuery<string[]>({
    queryKey: ["experiment", experimentId, "analysis-results", simulationPath],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/analysis/results`, {
          params: { simulation_path: simulationPath },
        })
        .then((r) => r.data),
    enabled: !!experimentId && !!simulationPath,
  })
}

export function useAnalysisVariants(
  experimentId: string,
  simulationPath: string | null,
  baseResultName: string | null
) {
  return useQuery<AnalysisVariant[]>({
    queryKey: ["experiment", experimentId, "analysis-variants", simulationPath, baseResultName],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/analysis/results/${baseResultName}/variants`, {
          params: { simulation_path: simulationPath },
        })
        .then((r) => r.data),
    enabled: !!experimentId && !!simulationPath && !!baseResultName,
  })
}
