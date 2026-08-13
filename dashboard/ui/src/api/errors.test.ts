import { describe, expect, it } from "vitest"

import { ApiError, toApiError } from "./errors"

describe("toApiError", () => {
  it("normalizes generated RFC 9457 errors", () => {
    const error = toApiError({
      status: 503,
      info: { type: "urn:mddash:upstream-unavailable", title: "Unavailable", detail: "Try later" },
    })

    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe("Try later")
    expect(error.type).toBe("urn:mddash:upstream-unavailable")
  })

  it("normalizes network failures without exposing internals", () => {
    expect(toApiError(new TypeError("Failed to fetch"))).toMatchObject({
      title: "Network unavailable",
      message: "Check your connection and retry.",
    })
  })
})
