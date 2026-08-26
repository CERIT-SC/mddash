import { useEffect, useRef } from "react"

import { toApiError } from "@/api/errors"
import {
  useDeleteAnalysisJob,
  useGetAnalysisJobLogs,
  useGetAnalysisResult,
  useListAnalysisJobs,
  useListAnalysisResults,
  useListAnalysisResultVariants,
  useSubmitAnalysisJob,
} from "@/api/generated/client"
import { JobStatus, type AnalysisJob, type AnalysisJobRequest } from "@/api/generated/models"
import { API_RUNTIME_BASE_URL } from "@/api/runtime"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

/** Poll interval while an analysis job is active; matches the run step. */
const ANALYSIS_POLL_MS = 5000

/** URL prefix of every analysis endpoint for this experiment (jobs, results, variants, data). */
const analysisQueryPrefix = (experimentId: string) =>
  `${API_RUNTIME_BASE_URL}/dash/api/experiments/${experimentId}/analysis`

/**
 * Matches every query in the analysis family for the experiment. Query keys
 * are URL-first arrays, so a plain array filter would only deep-equal the
 * jobs key ("/analysis" ≠ "/analysis/results"); prefix the URL instead.
 */
const analysisFamilyPredicate = (experimentId: string) => (query: { queryKey: readonly unknown[] }) =>
  typeof query.queryKey[0] === "string" && query.queryKey[0].startsWith(analysisQueryPrefix(experimentId))

/** True while the job still has work to do. */
const jobActive = (job: AnalysisJob) => job.status === JobStatus.RUNNING || job.status === JobStatus.PENDING

/**
 * Analysis jobs for one simulation. Polls while any job is RUNNING/PENDING so
 * the panel catches completions without a manual refresh.
 */
export function useAnalysisJobs(experimentId: string, simulationPath: string, pollMs = ANALYSIS_POLL_MS) {
  return useListAnalysisJobs(
    experimentId,
    { simulation_path: simulationPath },
    {
      query: {
        retry: false,
        refetchInterval: (query) => {
          const jobs = query.state.data?.status === 200 ? query.state.data.data : undefined
          return jobs?.some(jobActive) ? pollMs : false
        },
      },
    }
  )
}

/** Submit + cancel mutations for analysis jobs, wired to the panel's invalidations. */
export function useAnalysisMutations(experimentId: string) {
  const queryClient = useQueryClient()
  const onError = (error: unknown) => toast.error(toApiError(error).message)

  function invalidateAll() {
    void queryClient.invalidateQueries({ predicate: analysisFamilyPredicate(experimentId) })
  }

  const submit = useSubmitAnalysisJob({
    mutation: {
      onSuccess: () => {
        toast.success("Analysis job submitted")
        invalidateAll()
      },
      onError,
    },
  })
  const remove = useDeleteAnalysisJob({ mutation: { onSuccess: invalidateAll, onError } })

  return {
    submit: {
      isPending: submit.isPending,
      mutate: (
        simulationPath: string,
        analysis: AnalysisJobRequest["analysis"],
        preprocessingMode: AnalysisJobRequest["preprocessing_mode"]
      ) =>
        submit.mutate({
          experimentId,
          data: { simulation_path: simulationPath, analysis, preprocessing_mode: preprocessingMode },
        }),
    },
    remove: {
      isPending: remove.isPending,
      mutate: (jobId: string) => remove.mutate({ experimentId, jobId }),
    },
  }
}

/** Names of the result files already produced for this simulation. */
export function useAvailableAnalysisResults(experimentId: string, simulationPath: string) {
  return useListAnalysisResults(experimentId, { simulation_path: simulationPath }, { query: { retry: false } })
}

/** Named variants of a hasVariants analysis result; queried only when the base result exists. */
export function useAnalysisVariants(experimentId: string, simulationPath: string, baseResultName: string | null) {
  return useListAnalysisResultVariants(
    experimentId,
    baseResultName ?? "",
    { simulation_path: simulationPath },
    { query: { retry: false, enabled: baseResultName !== null } }
  )
}

/**
 * One typed analysis result; queried only when a result name is known to
 * exist. The response is the generated `AnalysisResult` union — the renderer
 * registry narrows it via its guards.
 */
export function useAnalysisData(experimentId: string, simulationPath: string, resultName: string | null) {
  return useGetAnalysisResult(
    experimentId,
    resultName ?? "",
    { simulation_path: simulationPath },
    { query: { retry: false, enabled: resultName !== null } }
  )
}

/** Logs for one analysis job. Polls while `live` so a running job's output streams in. */
export function useAnalysisLogs(experimentId: string, jobId: string | null, live: boolean, pollMs = ANALYSIS_POLL_MS) {
  return useGetAnalysisJobLogs(experimentId, jobId ?? "", undefined, {
    query: {
      retry: false,
      enabled: jobId !== null,
      refetchInterval: live ? pollMs : false,
      staleTime: live ? 0 : Infinity,
    },
  })
}

/**
 * Watches the "any job active" boolean and, on the true→false edge, refreshes
 * the analysis query family so the freshly produced results/variants show up.
 */
export function useInvalidateAnalysisListsOnComplete(experimentId: string, isActive: boolean) {
  const queryClient = useQueryClient()
  const wasActiveRef = useRef(false)
  useEffect(() => {
    if (wasActiveRef.current && !isActive) {
      void queryClient.invalidateQueries({ predicate: analysisFamilyPredicate(experimentId) })
    }
    wasActiveRef.current = isActive
  }, [isActive, queryClient, experimentId])
}
