// MD Engine types
export const Engine = { GMX: "GMX", AMBER: "AMBER" } as const
export type Engine = (typeof Engine)[keyof typeof Engine]

// Runtime configuration injected by Caddy via config.js
declare global {
  interface Window {
    MDDASH_CONFIG?: {
      basePath: string
      apiPath: string
      user: string
      defaultNotebooksRepo: string
      mdpositUrl: string
    }
  }
}

// Detect dev mode: config.js won't be loaded in dev, so MDDASH_CONFIG will be undefined
export const DEBUG = typeof window.MDDASH_CONFIG === "undefined"

// Use runtime config or fallback to dev defaults
export const BASE_PATH = window.MDDASH_CONFIG?.basePath ?? "/"
export const API_BASE = window.MDDASH_CONFIG?.apiPath ?? "/dash/api"
export const HUB_API_BASE = "/hub/api"
export const USER = window.MDDASH_CONFIG?.user ?? "dev-user"
export const DEFAULT_NOTEBOOKS_REPO =
  window.MDDASH_CONFIG?.defaultNotebooksRepo ?? "https://github.com/sb-ncbr/mddash-notebooks.git"
export const MDPOSIT_URL = window.MDDASH_CONFIG?.mdpositUrl ?? ""

// Sentinel value for ShadCN Select components that require non-empty string values
export const SELECT_NONE = "__none__"
