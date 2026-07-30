/**
 * Minimal JupyterHub REST API client.
 *
 * Mirrors the endpoints used by the stock templates' JS (jhapi.js / token.js):
 * start/stop server, user CRUD, token request/revoke. Auth is cookie-based;
 * mutating requests carry the rendered XSRF token in the X-XSRFToken header
 * (falling back to the _xsrf cookie value).
 */

export class HubApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
    this.name = "HubApiError"
  }
}

export interface HubServerModel {
  name: string
  ready: boolean
  /** True while the server process exists (including during startup). */
  active: boolean
  /** Current transition — "spawn" or "stop" — or null when stable. */
  pending: string | null
  url: string
  started: string | null
  stopped: string | null
  last_activity: string | null
  progress_url: string | null
}

export interface HubUserModel {
  name: string
  admin: boolean
  server: string | null
  pending: string | null
  created: string | null
  last_activity: string | null
  servers?: Record<string, HubServerModel>
}

export interface HubTokenModel {
  id: string
  note: string | null
  scopes: string[]
  created: string | null
  last_activity: string | null
  expires_at: string | null
}

export interface TokenRequestBody {
  note?: string
  expires_in?: number | null
  scopes?: string[]
}

function xsrfCookie(): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("_xsrf="))
    ?.split("=")[1]
}

function joinUrl(...parts: string[]): string {
  return parts
    .map((part, i) => (i === 0 ? part.replace(/\/+$/, "") : part.replace(/^\/+|\/+$/g, "")))
    .filter(Boolean)
    .join("/")
}

export class HubApi {
  private xsrf: string | undefined

  constructor(
    private baseUrl: string,
    xsrf?: string
  ) {
    this.xsrf = xsrf || xsrfCookie()
  }

  apiUrl(...path: string[]): string {
    return joinUrl(this.baseUrl, "api", ...path.map(encodeURIComponent))
  }

  private async request<T>(path: string[], init: RequestInit = {}, query = ""): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string>),
    }
    if (this.xsrf) headers["X-XSRFToken"] = this.xsrf

    let response: Response
    try {
      response = await fetch(this.apiUrl(...path) + query, { ...init, headers })
    } catch {
      throw new HubApiError(0, "Cannot reach JupyterHub. Check your network connection.")
    }
    if (response.ok) {
      if (response.status === 204) return undefined as T
      return (await response.json()) as T
    }
    let message = `JupyterHub request failed (${response.status})`
    try {
      const body = (await response.json()) as { message?: string }
      if (body.message) message = body.message
    } catch {
      // non-JSON error body — keep the generic message
    }
    throw new HubApiError(response.status, message)
  }

  getUser(name: string): Promise<HubUserModel> {
    return this.request(["users", name])
  }

  startServer(name: string): Promise<void> {
    return this.request(["users", name, "server"], { method: "POST" })
  }

  stopServer(name: string): Promise<void> {
    return this.request(["users", name, "server"], { method: "DELETE" })
  }

  listUsers(limit = 500): Promise<HubUserModel[]> {
    return this.request(["users"], {}, `?include_stopped_servers=true&limit=${limit}`)
  }

  addUser(name: string): Promise<HubUserModel> {
    return this.request(["users", name], { method: "POST" })
  }

  deleteUser(name: string): Promise<void> {
    return this.request(["users", name], { method: "DELETE" })
  }

  editUser(name: string, body: { admin: boolean }): Promise<HubUserModel> {
    return this.request(["users", name], { method: "PATCH", body: JSON.stringify(body) })
  }

  listTokens(name: string): Promise<{ api_tokens: HubTokenModel[] }> {
    return this.request(["users", name, "tokens"])
  }

  requestToken(name: string, body: TokenRequestBody): Promise<{ token: string }> {
    return this.request(["users", name, "tokens"], { method: "POST", body: JSON.stringify(body) })
  }

  revokeToken(name: string, tokenId: string): Promise<void> {
    return this.request(["users", name, "tokens", tokenId], { method: "DELETE" })
  }
}
