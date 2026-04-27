import axios from "axios"

import { API_BASE } from "@/util/const"

/**
 * Configured axios instance for the mddash API.
 * The backend returns raw resources on success and {detail} on error.
 * Status codes are the single source of truth for success/failure.
 */
export const api = axios.create({ baseURL: API_BASE })

/**
 * Raw axios instance for endpoints that return non-JSON responses (e.g. file downloads via send_file).
 * No response interceptor — use when the backend returns raw bytes.
 */
export const apiRaw = axios.create({ baseURL: API_BASE })

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const msg = error.response?.data?.detail ?? "Request failed."
    return Promise.reject(new Error(msg))
  }
)
