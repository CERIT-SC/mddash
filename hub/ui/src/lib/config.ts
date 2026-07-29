/**
 * Configuration injected by JupyterHub.
 *
 * Each built HTML entry is rendered by JupyterHub as a Jinja2 template. An
 * inline <script> in the entry HTML assigns `window.appConfig` from template
 * context values (via Jinja's `tojson` filter, so output is JS-safe JSON).
 *
 * In `vite dev` the Jinja expressions never render: the inline script is a
 * syntax error and `window.appConfig` stays undefined, so pages fall back to
 * these production-realistic defaults and remain fully browsable.
 */

declare global {
  interface Window {
    appConfig?: Record<string, unknown>
  }
}

export const DEV_FALLBACK_BASE_URL = "/hub/"

/** Template context available on every hub page (base_url, user, logout_url, …). */
export interface HubBaseConfig {
  baseUrl: string
  userName: string
  xsrf: string
  logoutUrl: string
  adminAccess: boolean
  announcement: string | null
}

const BASE_DEFAULTS: HubBaseConfig = {
  baseUrl: DEV_FALLBACK_BASE_URL,
  userName: "user",
  xsrf: "",
  logoutUrl: `${DEV_FALLBACK_BASE_URL}logout`,
  adminAccess: false,
  announcement: null,
}

export function getAppConfig<T extends object>(pageDefaults: T): T & HubBaseConfig {
  return { ...BASE_DEFAULTS, ...pageDefaults, ...(window.appConfig ?? {}) } as T & HubBaseConfig
}
