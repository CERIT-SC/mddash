export let API_RUNTIME_BASE_URL = ""

function deploymentPrefix(apiPath: string): string {
  if (!apiPath.endsWith("/dash/api")) throw new Error("apiPath must end with /dash/api")
  return apiPath.slice(0, -"/dash/api".length)
}

export function initializeApiRuntime(apiPath: string): void {
  API_RUNTIME_BASE_URL = deploymentPrefix(apiPath)
}
