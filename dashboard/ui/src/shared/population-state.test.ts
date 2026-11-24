import type { Population } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { pollWhilePopulationActive, populationPolling, populationReady } from "./population-state"

function population(status: Population["status"]): Population {
  return {
    operation_id: "op",
    experiment_id: "exp1",
    status,
    phase: "starting",
    files_present: 0,
    files_total: null,
    bytes_present: 0,
    bytes_total: null,
    byte_percentage: null,
    error: null,
  }
}

describe("populationReady", () => {
  it("is ready without a population or once the import succeeded", () => {
    expect(populationReady({ population: null })).toBe(true)
    expect(populationReady({ population: population("succeeded") })).toBe(true)
    expect(populationReady({ population: population("queued") })).toBe(false)
    expect(populationReady({ population: population("running") })).toBe(false)
    expect(populationReady({ population: population("cancelling") })).toBe(false)
    // durable terminal failures keep the experiment read-only until deletion
    expect(populationReady({ population: population("failed") })).toBe(false)
    expect(populationReady({ population: population("cancelled") })).toBe(false)
  })
})

describe("populationPolling", () => {
  it("polls only while the import is in flight", () => {
    expect(populationPolling(population("queued"))).toBe(true)
    expect(populationPolling(population("running"))).toBe(true)
    expect(populationPolling(population("cancelling"))).toBe(true)
    expect(populationPolling(population("succeeded"))).toBe(false)
    expect(populationPolling(population("failed"))).toBe(false)
    expect(populationPolling(population("cancelled"))).toBe(false)
    expect(populationPolling(null)).toBe(false)
    expect(populationPolling(undefined)).toBe(false)
  })
})

function poll(httpStatus: number | undefined, pop: Population | null | undefined) {
  return pollWhilePopulationActive(5000)({
    state: {
      data: httpStatus === undefined ? undefined : { status: httpStatus, data: { population: pop } },
    },
  })
}

describe("pollWhilePopulationActive", () => {
  it("polls only while a successfully fetched experiment is still populating", () => {
    expect(poll(200, population("queued"))).toBe(5000)
    expect(poll(200, population("running"))).toBe(5000)
    expect(poll(200, population("cancelling"))).toBe(5000)
    expect(poll(200, population("succeeded"))).toBe(false)
    expect(poll(200, null)).toBe(false)
    // a failed status fetch is handled by the durable error UI, not by polling
    expect(poll(500, population("queued"))).toBe(false)
    expect(poll(undefined, population("running"))).toBe(false)
  })
})
