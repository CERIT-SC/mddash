import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/http"

export type MdPositHandoffFile = {
  role: "structure" | "topology" | "trajectory"
  path: string
  url: string
}

export type MdPositHandoffResponse = {
  metadata_file: {
    path: string
    url: string
  }
  files: MdPositHandoffFile[]
  vre_lite_url: string | null
}

export type MdPositSelectedFiles = {
  structure: string
  topology: string
  trajectory: string
}

export function useMdPositPublishData(experimentId: string) {
  return useMutation<MdPositHandoffResponse, Error, MdPositSelectedFiles>({
    mutationFn: (files) =>
      api.post(`/experiments/${experimentId}/publish`, { target: "mdposit", files }).then((r) => r.data),
    onError: (error: Error) => toast.error(error.message),
  })
}
