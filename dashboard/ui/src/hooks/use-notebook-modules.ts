import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/http"
import type { NotebookModule } from "@/util/types"

export function useNotebookModules() {
  return useQuery<NotebookModule[]>({
    queryKey: ["notebook-modules"],
    queryFn: () => api.get("/notebook-modules").then((r) => r.data),
  })
}
