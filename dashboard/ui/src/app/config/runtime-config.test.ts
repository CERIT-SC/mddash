import { describe, expect, it } from "vitest"

import { parseRuntimeConfig } from "./runtime-config"

const productionConfig = {
  basePath: "/dash",
  apiPath: "/dash/api",
  user: "alice",
  defaultNotebooksRepo: "https://example.test/notebooks.git",
  mdpositUrl: "https://mdposit.example.test",
  hubHomeUrl: "/hub/home",
  hubTokenUrl: "/hub/token",
  logoutUrl: "/hub/logout",
}

describe("parseRuntimeConfig", () => {
  it("accepts and normalizes a root deployment", () => {
    expect(parseRuntimeConfig({ ...productionConfig, basePath: "/dash/", apiPath: "/dash/api/" })).toEqual(
      productionConfig
    )
  })

  it("accepts a nested deployment", () => {
    expect(
      parseRuntimeConfig({
        ...productionConfig,
        basePath: "/user/test/dash",
        apiPath: "/user/test/dash/api",
      })
    ).toMatchObject({ basePath: "/user/test/dash", apiPath: "/user/test/dash/api" })
  })

  it("rejects an API path outside the dashboard base path", () => {
    expect(() => parseRuntimeConfig({ ...productionConfig, apiPath: "/api" })).toThrow(
      "apiPath must equal basePath + /api"
    )
  })

  it("rejects external Hub routes", () => {
    expect(() => parseRuntimeConfig({ ...productionConfig, logoutUrl: "https://example.test/logout" })).toThrow()
  })
})
