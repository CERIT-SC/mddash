import { vi } from "vitest"

export type FetchCall = { url: string; method: string; body?: unknown }

export function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input
  return input instanceof URL ? input.href : input.url
}

export function mockFetch(...responses: Response[]): FetchCall[] {
  const queue = [...responses]
  const calls: FetchCall[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: requestUrl(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    return queue.shift() ?? new Response("[]", { status: 200 })
  })
  return calls
}

/** URL-suffix matched stub for parallel queries (e.g. wizard fires experiment + simulations). */
export function mockApiBySuffix(handlers: Record<string, Response>): FetchCall[] {
  const calls: FetchCall[] = []
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: requestUrl(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    })
    const url = requestUrl(input)
    for (const [suffix, response] of Object.entries(handlers)) {
      if (url.endsWith(suffix)) return response.clone()
    }
    return new Response(null, { status: 404 })
  })
  return calls
}
