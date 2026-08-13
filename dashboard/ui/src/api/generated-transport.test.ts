import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
  delete window.MDDASH_CONFIG
})

describe("generated listExperiments transport", () => {
  it("does not preempt standalone validation when runtime config is invalid", async () => {
    window.MDDASH_CONFIG = { basePath: "/wrong" }
    await expect(import("./runtime")).resolves.toBeDefined()
  })

  it.each([
    ["/dash", "/dash/api", "/dash/api/experiments"],
    ["/user/test/dash", "/user/test/dash/api", "/user/test/dash/api/experiments"],
  ])("requests the contract path for %s", async (basePath, apiPath, expectedUrl) => {
    window.MDDASH_CONFIG = {
      basePath,
      apiPath,
      user: "alice",
      defaultNotebooksRepo: "https://example.test/notebooks.git",
      mdpositUrl: "https://mdposit.example.test",
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    const { initializeApiRuntime } = await import("./runtime")
    initializeApiRuntime(basePath)
    const { listExperiments } = await import("./generated/client")
    await listExperiments()

    expect(fetchMock).toHaveBeenCalledWith(
      expectedUrl,
      expect.objectContaining({ credentials: "same-origin", method: "GET" })
    )
  })
})
