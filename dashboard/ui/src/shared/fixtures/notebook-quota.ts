import type { Experiment } from "@/api/generated/models"
import { withNotebook } from "@/shared/fixtures/experiment"
import { requestUrl, type FetchCall } from "@/shared/fixtures/mock-fetch"
import { expect, vi } from "vitest"

export const EXPERIMENTS_URL = "/dash/api/experiments"
export const NOTEBOOK_CONFIG_URL = "/dash/api/notebook-config"
const NOTEBOOK_QUOTA_EXCEEDED_TYPE = "urn:mddash:notebook-quota-exceeded"

export function notebookConfigResponse(concurrentLimit: number = 2): Response {
  return Response.json({
    tiers: [{ value: "1x", cpuLimit: "2", memoryLimit: "4Gi" }],
    defaultTier: "1x",
    concurrentLimit,
  })
}

type NotebookQuotaApiOptions = {
  limit: number
  /** GET /experiments content; a notebook DELETE flips that experiment to DOWN. */
  experiments: Experiment[]
  /** Notebook start POSTs are rejected with the quota 403 (fallback path). */
  startFails?: boolean
  /** GET /experiments never resolves (loading state). */
  listNeverResolves?: boolean
  /** GET /notebook-config never resolves — the limit stays unknown client-side. */
  configNeverResolves?: boolean
}

/**
 * Stateful quota mock: DELETE flips a notebook to DOWN; `served` tracks answered
 * URLs so proactive-path tests can wait for the quota queries to settle.
 */
export function mockNotebookQuotaApi({
  limit,
  experiments,
  startFails = false,
  listNeverResolves = false,
  configNeverResolves = false,
}: NotebookQuotaApiOptions) {
  const calls: FetchCall[] = []
  const served = new Set<string>()
  let current = experiments
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input)
    const method = init?.method ?? "GET"
    calls.push({
      url,
      method,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    const notebookMatch = url.match(/\/experiments\/([^/]+)\/notebook$/)
    if (notebookMatch) {
      served.add(url)
      if (method === "DELETE") {
        const id = notebookMatch[1]
        current = current.map((exp) => (exp.id === id ? { ...exp, notebook: withNotebook("DOWN", id) } : exp))
        return new Response(null, { status: 204 })
      }
      if (method === "POST") {
        return startFails
          ? Response.json(
              {
                type: NOTEBOOK_QUOTA_EXCEEDED_TYPE,
                title: "Forbidden",
                detail: `Maximum of ${limit} concurrent notebook(s) reached. Stop one first.`,
                solution: "Stop another notebook first, then start this one.",
              },
              { status: 403 }
            )
          : Response.json({}, { status: 201 })
      }
    }
    if (url.endsWith(NOTEBOOK_CONFIG_URL)) {
      if (configNeverResolves) return new Promise<Response>(() => undefined)
      served.add(NOTEBOOK_CONFIG_URL)
      return notebookConfigResponse(limit)
    }
    if (url.endsWith(EXPERIMENTS_URL)) {
      if (listNeverResolves) return new Promise<Response>(() => undefined)
      served.add(EXPERIMENTS_URL)
      return Response.json(current)
    }
    return new Response(null, { status: 404 })
  })

  async function quotaSettled(): Promise<void> {
    await vi.waitFor(() => {
      expect(served.has(NOTEBOOK_CONFIG_URL)).toBe(true)
      expect(served.has(EXPERIMENTS_URL)).toBe(true)
    })
  }

  return { calls, served, quotaSettled }
}
