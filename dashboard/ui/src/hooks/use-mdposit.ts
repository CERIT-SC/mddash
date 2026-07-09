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

export function useMdPositPublishData(experimentId: string) {
  return useMutation<MdPositHandoffResponse, Error, string>({
    mutationFn: (simulationPath) =>
      api
        .post(`/experiments/${experimentId}/publish`, { target: "mdposit", simulation_path: simulationPath })
        .then((r) => r.data),
    onError: (error: Error) => toast.error(error.message),
  })
}
