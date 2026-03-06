import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import type { AnalysisJob, AnalysisResultMeta } from "@/util/analysis-types"

export function useAnalysisJobs(experimentId: string) {
  return useQuery<AnalysisJob[]>({
    queryKey: ["experiment", experimentId, "analysis"],
    queryFn: () => api.get(`/experiments/${experimentId}/analysis`).then((r) => r.data),
    enabled: !!experimentId,
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
  structure_file: string
  trajectory_file: string
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
      queryClient.invalidateQueries({ queryKey: ["experiment", experimentId, "analysis-results"] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
}

export function useAnalysisResults(experimentId: string) {
  return useQuery<AnalysisResultMeta[]>({
    queryKey: ["experiment", experimentId, "analysis-results"],
    queryFn: () => api.get(`/experiments/${experimentId}/analysis/results`).then((r) => r.data),
    enabled: !!experimentId,
  })
}

export function useAnalysisData(experimentId: string, analysisName: string | null) {
  return useQuery<unknown>({
    queryKey: ["experiment", experimentId, "analysis-results", analysisName],
    queryFn: () => api.get(`/experiments/${experimentId}/analysis/results/${analysisName}`).then((r) => r.data),
    enabled: !!experimentId && !!analysisName,
  })
}
