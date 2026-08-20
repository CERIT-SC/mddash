import { Engine, JobStatus, type TunerJob, type TunerTrial } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { formatCost, formatHardware, jobLive, parseTrial, suggest, type TrialRow } from "./tuned-trials"

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

describe("jobLive", () => {
  const base: TunerJob = {
    id: "j1",
    experiment_id: "exp1",
    simulation_path: "md.simulation.json",
    nsteps: 25000,
    created_at: "2026-08-19T00:00:00Z",
    is_stopped: false,
    engine: Engine.GMX,
    tuner_status: JobStatus.RUNNING,
    sim_length_ns: 100,
    trials: [],
  }

  it("is live for pending/running/unknown, never when stopped or finished", () => {
    expect(jobLive({ ...base, tuner_status: JobStatus.RUNNING })).toBe(true)
    expect(jobLive({ ...base, tuner_status: JobStatus.PENDING })).toBe(true)
    expect(jobLive({ ...base, tuner_status: JobStatus.FINISHED })).toBe(false)
    expect(jobLive({ ...base, is_stopped: true })).toBe(false)
    // Stopped jobs report UNKNOWN from the API fallback.
    expect(jobLive({ ...base, is_stopped: true, tuner_status: JobStatus.UNKNOWN })).toBe(false)
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
