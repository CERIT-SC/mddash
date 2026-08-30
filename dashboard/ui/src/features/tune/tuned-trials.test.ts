import { Engine, JobStatus, type TunerTrial } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { formatCost, formatHardware, parseTrial, sortTrials, suggest, type TrialRow } from "./tuned-trials"

function rawTrial(overrides: Record<string, unknown> = {}): TunerTrial {
  return {
    id: "t1",
    status: JobStatus.FINISHED,
    performance: 100,
    estimated_time: 1,
    estimated_cost: 2,
    np: 1,
    ntomp: 2,
    pme: "gpu",
    nb: "cpu",
    ...overrides,
  }
}

function row(overrides: Partial<TrialRow> = {}): TrialRow {
  return {
    id: "t1",
    status: JobStatus.FINISHED,
    performance: 100,
    estTimeHours: 1,
    estCost: 2,
    np: 1,
    ntomp: 1,
    pme: "gpu",
    nb: "gpu",
    binary: null,
    ewald: null,
    ...overrides,
  }
}

describe("parseTrial", () => {
  it("parses a full GMX trial", () => {
    const parsed = parseTrial(Engine.GMX, rawTrial())
    expect(parsed).toMatchObject({ id: "t1", performance: 100, estTimeHours: 1, estCost: 2, pme: "gpu", nb: "cpu" })
  })

  it("blanks only the malformed field, not the whole row", () => {
    const parsed = parseTrial(Engine.GMX, rawTrial({ np: "eight" }))
    expect(parsed).toMatchObject({ np: null, ntomp: 2, pme: "gpu", nb: "cpu" })
  })

  it("keeps the row but blanks cells when engine fields are missing", () => {
    const parsed = parseTrial(Engine.GMX, rawTrial({ pme: undefined, nb: undefined, np: undefined, ntomp: undefined }))
    expect(parsed).toMatchObject({ id: "t1", pme: null, nb: null, np: null, ntomp: null })
  })

  it("drops rows with an unusable base", () => {
    expect(parseTrial(Engine.GMX, rawTrial({ id: undefined }))).toBeNull()
  })

  it("parses AMBER fields", () => {
    const parsed = parseTrial(
      Engine.AMBER,
      rawTrial({ pme: undefined, nb: undefined, binary: "pmemd.cuda", ewald: "optimized" })
    )
    expect(parsed).toMatchObject({ binary: "pmemd.cuda", ewald: "optimized", pme: null })
  })
})

describe("suggest", () => {
  it("picks max performance as fastest and min cost as eco", () => {
    const rows = [
      row({ id: "slow-cheap", performance: 40, estCost: 1 }),
      row({ id: "fast", performance: 700, estCost: 3 }),
      row({ id: "mid", performance: 500, estCost: 2 }),
    ]
    expect(suggest(rows)).toEqual({ fastestId: "fast", ecoId: "slow-cheap" })
  })

  it("lets the same config be both fastest and cheapest, even alone", () => {
    const rows = [
      row({ id: "fast-cheap", performance: 700, estCost: 1 }),
      row({ id: "slow", performance: 100, estCost: 2 }),
    ]
    expect(suggest(rows)).toEqual({ fastestId: "fast-cheap", ecoId: "fast-cheap" })
    expect(suggest([row({ id: "only", estCost: 5 })])).toEqual({ fastestId: "only", ecoId: "only" })
  })

  it("marks the single cost-bearing trial as eco", () => {
    const rows = [
      row({ id: "no-cost", performance: 700, estCost: null }),
      row({ id: "cost", performance: 100, estCost: 2 }),
    ]
    expect(suggest(rows)).toEqual({ fastestId: "no-cost", ecoId: "cost" })
  })

  it("ignores unfinished trials and null costs", () => {
    const rows = [
      row({ id: "running", status: JobStatus.RUNNING, performance: null, estCost: null }),
      row({ id: "no-cost", performance: 999, estCost: null }),
    ]
    expect(suggest(rows)).toEqual({ fastestId: "no-cost", ecoId: null })
  })
})

describe("sortTrials", () => {
  it("keeps performance the primary metric, best first", () => {
    const rows = [
      row({ id: "pending", status: JobStatus.PENDING, performance: null }),
      row({ id: "mid", performance: 500 }),
      row({ id: "fast", performance: 700 }),
      row({ id: "running", status: JobStatus.RUNNING, performance: null }),
      row({ id: "slow", performance: 40 }),
    ]
    expect(sortTrials(rows).map((r) => r.id)).toEqual(["fast", "mid", "slow", "running", "pending"])
  })

  it("orders result-less trials finished > error > running > pending", () => {
    const rows = [
      row({ id: "pending", status: JobStatus.PENDING, performance: null }),
      row({ id: "running", status: JobStatus.RUNNING, performance: null }),
      row({ id: "error", status: JobStatus.ERROR, performance: null }),
      // Early-stopped trials finish without a measured performance.
      row({ id: "early-stopped", status: JobStatus.FINISHED, performance: null }),
    ]
    expect(sortTrials(rows).map((r) => r.id)).toEqual(["early-stopped", "error", "running", "pending"])
  })
})

describe("formatting", () => {
  it("formats cost with trailing zeros trimmed", () => {
    expect(formatCost(2.6)).toBe("$2.6")
    expect(formatCost(0.04)).toBe("$0.04")
    expect(formatCost(10)).toBe("$10")
  })

  it("uppercases hardware values and dashes nulls", () => {
    expect(formatHardware("gpu")).toBe("GPU")
    expect(formatHardware(null)).toBe("—")
  })
})
