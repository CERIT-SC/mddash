import { DEV_RUNTIME_CONFIG, parseRuntimeConfig, type RuntimeConfig } from "./runtime-config"

export function loadRuntimeConfig(): RuntimeConfig {
  const value = import.meta.env.DEV ? (window.MDDASH_CONFIG ?? DEV_RUNTIME_CONFIG) : window.MDDASH_CONFIG
  return parseRuntimeConfig(value)
}
