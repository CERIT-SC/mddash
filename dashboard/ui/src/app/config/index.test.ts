import { afterEach, describe, expect, it, vi } from "vitest"

import { loadRuntimeConfig } from "."

afterEach(() => vi.unstubAllGlobals())

describe("loadRuntimeConfig", () => {
  it("does not hide an invalid runtime configuration", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ basePath: "/wrong" })))

    await expect(loadRuntimeConfig()).rejects.toThrow()
  })
})
