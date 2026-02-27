import axios from "axios"

import { API_BASE } from "@/util/const"

/**
 * Configured axios instance for the mddash API.
 * Interceptors unwrap the backend envelope `{ success, data, message }`
 * so queryFns receive the payload directly and errors are thrown as Error objects.
 */
export const api = axios.create({ baseURL: API_BASE })

/**
 * Raw axios instance for endpoints that return non-envelope responses (e.g. file downloads via send_file).
 * No response interceptor — use when the backend returns raw bytes instead of `{ success, data }`.
 */
export const apiRaw = axios.create({ baseURL: API_BASE })

api.interceptors.response.use(
  (res) => ({ ...res, data: res.data?.data ?? null }),
  (error) => {
    const msg = error.response?.data?.message ?? "Request failed."
    return Promise.reject(new Error(msg))
  }
)
