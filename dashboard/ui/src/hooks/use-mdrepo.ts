import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"
import { API_BASE } from "@/util/const"

interface MDRepoStatus {
  authenticated: boolean
  mdrepo_url?: string
}

export interface PublishResponse {
  id: string
  links?: {
    edit_html?: string
    self_html?: string
  }
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
