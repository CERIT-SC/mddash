import { DEV_RUNTIME_CONFIG, parseRuntimeConfig, type RuntimeConfig } from "./runtime-config"

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  const response = await fetch("runtime-config.json", { cache: "no-store", credentials: "same-origin" })
  if (!response.ok) {
    if (import.meta.env.DEV && response.status === 404) return DEV_RUNTIME_CONFIG
    throw new Error("Runtime configuration is unavailable")
  }
  return parseRuntimeConfig(await response.json())
}
