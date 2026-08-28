import { Engine, type AmberJob, type GromacsJob } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { jobConfigRequest } from "./use-simulation-job"

// pme/nb/binary/ewald are non-nullable columns server-side — every stored job carries them.
function gmxJob(overrides: Partial<GromacsJob> = {}): GromacsJob {
  return {
    id: "job1",
    experiment_id: "exp1",
    simulation_path: "md.simulation.json",
    engine: Engine.GMX,
    np: 4,
    ntomp: 2,
    pme: "gpu",
    nb: "cpu",
    status: "FINISHED",
    ...overrides,
  } as GromacsJob
}

function amberJob(overrides: Partial<AmberJob> = {}): AmberJob {
  return {
    ...gmxJob(overrides),
    engine: Engine.AMBER,
    binary: "pmemd.MPI",
    ewald: "optimized",
  } as AmberJob
}

describe("jobConfigRequest", () => {
  it("rebuilds the GMX request from the stored job", () => {
    expect(jobConfigRequest(Engine.GMX, gmxJob())).toEqual({ pme: "gpu", nb: "cpu", np: 4, ntomp: 2 })
  })

  it("rebuilds the AMBER request from the stored job", () => {
    expect(jobConfigRequest(Engine.AMBER, amberJob())).toEqual({
      binary: "pmemd.MPI",
      ewald: "optimized",
      np: 4,
      ntomp: 2,
    })
  })
})
