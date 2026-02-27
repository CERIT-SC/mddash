import { useQuery } from "@tanstack/react-query"

import { api, apiRaw } from "@/lib/http"
import type { FileOption } from "@/util/types"

export async function getFile(experimentId: string, path: string): Promise<File> {
  const response = await apiRaw.get(`/experiments/${experimentId}/files/${path}`, {
    responseType: "blob",
  })
  return new File([response.data], path, { type: response.headers["content-type"] })
}

export function useFiles(experimentId: string, ext?: string | string[]) {
  return useQuery<FileOption[]>({
    queryKey: ["experiment", experimentId, "files", ext],
    queryFn: () =>
      api
        .get(`/experiments/${experimentId}/files`, {
          params: ext ? { ext: Array.isArray(ext) ? ext.join(",") : ext } : {},
        })
        .then((r) => r.data),
    enabled: !!experimentId,
  })
}
