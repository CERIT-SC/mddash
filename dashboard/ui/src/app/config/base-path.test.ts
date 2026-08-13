import { describe, expect, it } from "vitest"

import { deriveDashboardBasePath } from "./base-path"

describe("deriveDashboardBasePath", () => {
  it.each([
    ["/dash/", "/dash/"],
    ["/dash/experiments", "/dash/"],
    ["/user/test/dash/", "/user/test/dash/"],
    ["/user/test/dash/missing", "/user/test/dash/"],
  ])("derives %s as %s", (pathname, expected) => {
    expect(deriveDashboardBasePath(pathname)).toBe(expected)
  })

  it("returns the root fallback when the dashboard segment is absent", () => {
    expect(deriveDashboardBasePath("/unrelated")).toBe("/")
  })
})
