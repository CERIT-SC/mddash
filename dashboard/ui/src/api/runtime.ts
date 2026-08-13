export let API_RUNTIME_BASE_URL = ""

export function deploymentPrefix(basePath: string): string {
  if (!basePath.endsWith("/dash")) throw new Error("basePath must end with /dash")
  return basePath.slice(0, -"/dash".length)
}

export function initializeApiRuntime(basePath: string): void {
  API_RUNTIME_BASE_URL = deploymentPrefix(basePath)
}
