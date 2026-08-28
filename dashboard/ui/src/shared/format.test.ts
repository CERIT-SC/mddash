import { describe, expect, it } from "vitest"

import { formatBytes, formatDate, formatTime, relativeTime } from "./format"

describe("formatTime", () => {
  it("shows the two most significant units compactly", () => {
    expect(formatTime(0)).toBe("0s")
    expect(formatTime(45)).toBe("45s")
    expect(formatTime(540)).toBe("9m")
    expect(formatTime(772)).toBe("12m 52s")
    expect(formatTime(9600)).toBe("2h 40m")
    expect(formatTime(97200)).toBe("1d 3h")
    expect(formatTime(3600)).toBe("1h")
  })
})

describe("formatBytes", () => {
  it("formats sizes", () => {
    expect(formatBytes(0)).toBe("0 KB")
    expect(formatBytes(15 * 1024 ** 2)).toBe("15 MB")
    expect(formatBytes(8.7 * 1024 ** 3)).toBe("8.7 GB")
  })
})

describe("formatDate", () => {
  it("formats ISO timestamps as short dates", () => {
    expect(formatDate("2026-07-20T13:43:20Z")).toBe("Jul 20, 2026")
    expect(formatDate("2026-01-05T00:00:00Z")).toBe("Jan 5, 2026")
  })
})

describe("relativeTime", () => {
  const now = new Date("2026-08-14T12:00:00Z").getTime()

  it("formats ages", () => {
    expect(relativeTime("2026-08-14T11:59:30Z", now)).toBe("just now")
    expect(relativeTime("2026-08-14T11:48:00Z", now)).toBe("12 min ago")
    expect(relativeTime("2026-08-14T07:00:00Z", now)).toBe("5 h ago")
    expect(relativeTime("2026-08-13T12:00:00Z", now)).toBe("yesterday")
    expect(relativeTime("2026-08-06T12:00:00Z", now)).toBe("8 days ago")
  })
})
