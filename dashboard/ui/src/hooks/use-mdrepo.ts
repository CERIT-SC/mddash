import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import { API_BASE } from "@/util/const"
import type { PublishResponse, PublishStatus } from "@/util/types"

interface MDRepoStatus {
  authenticated: boolean
  mdrepo_url?: string
}

export function getMDRepoAuthUrl(returnUrl: string): string {
  return `${API_BASE}/mdrepo/auth?return_url=${encodeURIComponent(returnUrl)}`
}

export function useMDRepoStatus() {
  return useQuery<MDRepoStatus>({
    queryKey: ["mdrepo", "status"],
    queryFn: () => api.get("/mdrepo/status").then((r) => r.data),
  })
}

export function usePublishExperiment() {
  return useMutation<PublishResponse, Error, string>({
    mutationFn: (id) => api.post(`/experiments/${id}/publish`).then((r) => r.data),
    onError: (error: Error) => toast.error(error.message),
  })
}

export function usePublishStatus(experimentId: string | undefined, enabled: boolean) {
  return useQuery<PublishStatus>({
    queryKey: ["publish", "status", experimentId],
    queryFn: () => api.get(`/experiments/${experimentId}/publish/status`).then((r) => r.data),
    enabled: !!experimentId && enabled,
    refetchInterval: (query) => {
      const state = query.state.data?.upload_state
      if (state === "queued" || state === "running") {
        return 3000
      }
      return false
    },
  })
}
