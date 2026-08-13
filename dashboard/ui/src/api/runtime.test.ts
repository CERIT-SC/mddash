import { describe, expect, it } from "vitest"

import { API_RUNTIME_BASE_URL, deploymentPrefix, initializeApiRuntime } from "./runtime"

describe("deploymentPrefix", () => {
  it.each([
    ["/dash", ""],
    ["/user/test/dash", "/user/test"],
  ])("derives the generated API prefix from %s", (basePath, expected) => {
    expect(deploymentPrefix(basePath)).toBe(expected)
  })

  it("rejects a base path without terminal /dash", () => {
    expect(() => deploymentPrefix("/user/test")).toThrow("basePath must end with /dash")
  })

  it("is initialized explicitly by the application composition root", () => {
    initializeApiRuntime("/user/alice/dash")
    expect(API_RUNTIME_BASE_URL).toBe("/user/alice")
  })
})
