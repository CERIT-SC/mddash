import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe("generated listExperiments transport", () => {
  it.each([
    ["/dash/api", "/dash/api/experiments"],
    ["/user/test/dash/api", "/user/test/dash/api/experiments"],
  ])("requests the contract path for %s", async (apiPath, expectedUrl) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    const { initializeApiRuntime } = await import("./runtime")
    initializeApiRuntime(apiPath)
    const { listExperiments } = await import("./generated/client")
    await listExperiments()

    expect(fetchMock).toHaveBeenCalledWith(
      expectedUrl,
      expect.objectContaining({ credentials: "same-origin", method: "GET" })
    )
  })
})
