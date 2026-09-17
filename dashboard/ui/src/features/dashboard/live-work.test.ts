import type { AnalysisJob, SimulationJob, TunerJob } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { describe, expect, it } from "vitest"

import { hasLiveWork, isAnalysisJobLive } from "./live-work"

const simJob = (status: SimulationJob["status"], isLive: boolean): SimulationJob =>
  ({ status, is_live: isLive, created_at: "2026-08-13T00:00:00Z" }) as SimulationJob

const tunerJob = (isLive: boolean): TunerJob =>
  ({
    is_live: isLive,
    tuner_status: isLive ? "RUNNING" : "FINISHED",
    created_at: "2026-08-13T00:00:00Z",
    trials: [],
  }) as TunerJob

const analysisJob = (status: AnalysisJob["status"]): AnalysisJob =>
  ({ status, created_at: "2026-08-13T00:00:00Z" }) as AnalysisJob

describe("hasLiveWork", () => {
  it("is false with no jobs and with only terminal jobs", () => {
    expect(hasLiveWork(experiment("e1"))).toBe(false)
    expect(
      hasLiveWork(
        experiment("e1", {
          simulation_jobs: [simJob("FINISHED", false)],
          tuner_jobs: [tunerJob(false)],
          analysis_jobs: [analysisJob("FINISHED"), analysisJob("ERROR")],
        })
      )
    ).toBe(false)
  })

  it("follows the server is_live flag on simulation and tuner jobs, including UNKNOWN", () => {
    // Server-side UNKNOWN counts as live (transient upstream failures) — the
    // payloads already say so; the client must not re-decide from the status.
    expect(hasLiveWork(experiment("e1", { simulation_jobs: [simJob("UNKNOWN", true)] }))).toBe(true)
    expect(hasLiveWork(experiment("e1", { tuner_jobs: [tunerJob(true)] }))).toBe(true)
    expect(hasLiveWork(experiment("e1", { simulation_jobs: [simJob("UNKNOWN", false)] }))).toBe(false)
  })

  it("treats UNKNOWN analysis jobs as live", () => {
    for (const status of ["PENDING", "RUNNING", "UNKNOWN"] as const) {
      expect(isAnalysisJobLive(analysisJob(status))).toBe(true)
      expect(hasLiveWork(experiment("e1", { analysis_jobs: [analysisJob(status)] }))).toBe(true)
    }
  })
})
