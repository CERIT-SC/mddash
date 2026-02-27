import { useQuery } from "@tanstack/react-query"
import axios from "axios"

import { api } from "@/lib/http"
import { API_BASE } from "@/util/const"
import type { FileOption } from "@/util/types"

export async function getFile(experimentId: string, path: string): Promise<File> {
  const response = await axios.get(`${API_BASE}/experiments/${experimentId}/files/${path}`, {
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
