import { toApiError } from "@/api/errors"
import {
  getGetExperimentQueryKey,
  getGetNotebookQueryKey,
  getListExperimentsQueryKey,
  useGetNotebook,
  useGetNotebookConfig,
  useListExperiments,
} from "@/api/generated/client"
import type { Notebook } from "@/api/generated/models"
import { isNotebookActive } from "@/shared/pod-status"
import { useQuery, useQueryClient } from "@tanstack/react-query"

// Transitioning pods get a fast poll so the UI follows them closely; steady
// state needs only an occasional check (idle-culling, starts from elsewhere).
const TRANSITION_POLL_MS = 3000
const STEADY_POLL_MS = 30_000
// Serving probes back off to a 30s ceiling (no hard give-up — slow binder
// installs take minutes); enough failures degrade the label in consumers.
const PROBE_MAX_DELAY_MS = 30_000
const TRANSITIONING = new Set<string>(["PENDING", "TERMINATING"])

export function useNotebook(experimentId: string) {
  return useGetNotebook(experimentId, {
    query: {
      retry: false,
      refetchInterval: (query) => {
        const data = query.state.data?.status === 200 ? query.state.data.data : undefined
        return data !== undefined && TRANSITIONING.has(data.status) ? TRANSITION_POLL_MS : STEADY_POLL_MS
      },
    },
  })
}

/**
 * Readiness of a RUNNING notebook: RUNNING only means the container started —
 * Jupyter (or binder installs) lags behind, so the probe retries without giving
 * up. started_at in the key re-probes restarts.
 */
export function useNotebookReady(experimentId: string, notebook: Notebook | undefined) {
  const running = notebook?.status === "RUNNING"
  const sessionKey = running ? `${experimentId}:${notebook.started_at ?? ""}` : null
  const probe = useQuery({
    queryKey: ["notebook-probe", sessionKey],
    enabled: sessionKey !== null,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 0,
    retry: Number.POSITIVE_INFINITY,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, PROBE_MAX_DELAY_MS),
    queryFn: async () => {
      // enabled implies RUNNING, so notebook and its path are defined here.
      const response = await fetch(notebook!.path, { credentials: "same-origin" })
      if (!response.ok) throw new Error(`Notebook not ready (${response.status})`)
      return true
    },
  })
  return { ready: probe.data === true, probeFailures: probe.failureCount }
}

export function useNotebookInvalidation(experimentId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: getGetNotebookQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experimentId) })
    void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
  }
}

const QUOTA_POLL_MS = 3000

/** True only for the API's concurrent-notebook limit problem — not other 403s (quota headroom etc.). */
export function isNotebookQuotaError(error: unknown): boolean {
  return toApiError(error).type === "urn:mddash:notebook-quota-exceeded"
}

/**
 * Cross-experiment notebook quota: the API-declared concurrent limit plus the
 * running count derived from the experiments list. `full` is only true when
 * both are known and every slot is taken — unknown state never blocks starts.
 */
export function useNotebookQuota({ poll = false }: { poll?: boolean } = {}) {
  const config = useGetNotebookConfig({ query: { retry: false } })
  const list = useListExperiments({
    query: { retry: false, refetchInterval: poll ? QUOTA_POLL_MS : undefined },
  })
  const limit = config.data?.status === 200 ? config.data.data.concurrentLimit : undefined
  const experiments = list.data?.status === 200 ? list.data.data : undefined
  const runningCount = experiments?.filter((experiment) => isNotebookActive(experiment.notebook?.status)).length
  return {
    limit,
    experiments,
    runningCount,
    full: limit !== undefined && runningCount !== undefined && runningCount >= limit,
  }
}
