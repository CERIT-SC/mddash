import type { AnalysisJob, SimulationJob, TunerJob } from "@/api/generated/models"
import { experiment } from "@/shared/fixtures/experiment"
import { describe, expect, it } from "vitest"

import { hasLiveWork, isAnalysisJobLive } from "./live-work"

const simJob = (status: SimulationJob["status"], isLive: boolean): SimulationJob => ({
  id: "s1",
  experiment_id: "e1",
  simulation_path: "md.simulation.json",
  created_at: "2026-08-13T00:00:00Z",
  engine: "GMX",
  np: 1,
  ntomp: 1,
  status,
  is_live: isLive,
})

const tunerJob = (isLive: boolean): TunerJob => ({
  id: "t1",
  experiment_id: "e1",
  simulation_path: "md.simulation.json",
  nsteps: 25000,
  created_at: "2026-08-13T00:00:00Z",
  is_stopped: !isLive,
  engine: "GMX",
  tuner_status: isLive ? "RUNNING" : "FINISHED",
  is_live: isLive,
  sim_length_ns: 100,
  trials: [],
})

const analysisJob = (status: AnalysisJob["status"]): AnalysisJob => ({
  id: "a1",
  experiment_id: "e1",
  simulation_path: "md.simulation.json",
  analysis_name: "rmsds",
  created_at: "2026-08-13T00:00:00Z",
  status,
})

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
    // The payload already encodes liveness — the client must not re-decide
    // from a status set (UNKNOWN is live server-side on transient failures).
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
