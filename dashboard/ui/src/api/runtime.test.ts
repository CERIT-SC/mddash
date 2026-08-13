import { describe, expect, it } from "vitest"

import { API_RUNTIME_BASE_URL, deploymentPrefix, initializeApiRuntime } from "./runtime"

describe("deploymentPrefix", () => {
  it.each([
    ["/dash/api", ""],
    ["/user/test/dash/api", "/user/test"],
  ])("derives the generated API prefix from %s", (apiPath, expected) => {
    expect(deploymentPrefix(apiPath)).toBe(expected)
  })

  it("rejects an unexpected API path", () => {
    expect(() => deploymentPrefix("/user/test/api")).toThrow("apiPath must end with /dash/api")
  })

  it("initializes the generated client base URL", () => {
    initializeApiRuntime("/user/alice/dash/api")
    expect(API_RUNTIME_BASE_URL).toBe("/user/alice")
  })
})
