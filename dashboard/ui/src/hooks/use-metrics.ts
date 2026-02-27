import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/http"
import type { ResourceUsage } from "@/util/types"

export function useMetrics() {
  return useQuery<ResourceUsage>({
    queryKey: ["metrics"],
    queryFn: () => api.get("/metrics").then((r) => r.data),
    refetchInterval: 30_000,
  })
}
