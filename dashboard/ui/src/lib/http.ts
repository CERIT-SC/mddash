import axios from "axios"

import { API_BASE } from "@/util/const"

/** Configured axios instance for the mddash API. */
export const api = axios.create({ baseURL: API_BASE })

/** Raw axios instance for non-JSON responses (e.g. file downloads via send_file). */
export const apiRaw = axios.create({ baseURL: API_BASE })

/** RFC 9457 problem-details error body returned by the backend. */
export interface ProblemDetails {
  type: string
  title: string
  detail: string
  solution?: string
}

/**
 * Error wrapping a problem-details response. `message` is the toast line
 * (`solution ?? detail ?? title`) so `toast.error(error.message)` shows the
 * actionable line when a solution is present.
 */
export class ApiError extends Error {
  constructor(
    public type: string,
    public title: string,
    public status: number,
    detail: string,
    public solution?: string
  ) {
    super(solution ?? detail ?? "Request failed.")
    this.name = "ApiError"
  }
}

function problemInterceptor(error: unknown) {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0
    const data = error.response?.data
    const p = data && typeof data === "object" ? (data as Partial<ProblemDetails>) : {}
    return Promise.reject(
      new ApiError(
        p.type ?? "urn:mddash:internal-error",
        p.title ?? "",
        status,
        p.detail ?? "Request failed.",
        p.solution
      )
    )
  }
  return Promise.reject(error instanceof Error ? error : new Error("Request failed."))
}

api.interceptors.response.use((res) => res, problemInterceptor)
apiRaw.interceptors.response.use((res) => res, problemInterceptor)
