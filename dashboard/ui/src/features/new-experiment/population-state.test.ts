import { describe, expect, it } from "vitest"

import { pollWhilePopulationActive, populationActive } from "./population-state"

describe("populationActive", () => {
  it("is active only for queued and running operations", () => {
    expect(populationActive("queued")).toBe(true)
    expect(populationActive("running")).toBe(true)
    expect(populationActive("succeeded")).toBe(false)
    expect(populationActive("failed")).toBe(false)
    expect(populationActive(null)).toBe(false)
    expect(populationActive(undefined)).toBe(false)
  })
})

function poll(httpStatus: number | undefined, status: string | undefined) {
  return pollWhilePopulationActive(3000)({
    state: {
      data: httpStatus === undefined ? undefined : { status: httpStatus, data: { status } },
    },
  })
}

describe("pollWhilePopulationActive", () => {
  it("polls only while a successfully fetched status is still active", () => {
    expect(poll(200, "queued")).toBe(3000)
    expect(poll(200, "running")).toBe(3000)
    expect(poll(200, "succeeded")).toBe(false)
    expect(poll(200, "failed")).toBe(false)
    // a failed status fetch is handled by the durable error UI, not by polling
    expect(poll(500, "queued")).toBe(false)
    expect(poll(undefined, undefined)).toBe(false)
  })
})
