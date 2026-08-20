import { Engine } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { toJobRequest } from "./hardware-config-form"

describe("toJobRequest", () => {
  it("maps GMX values to the GromacsJobRequest shape", () => {
    expect(toJobRequest(Engine.GMX, { pickA: "gpu", pickB: "cpu", np: 1, ntomp: 2 })).toEqual({
      pme: "gpu",
      nb: "cpu",
      np: 1,
      ntomp: 2,
    })
  })

  it("maps AMBER values to the AmberJobRequest shape", () => {
    expect(toJobRequest(Engine.AMBER, { pickA: "pmemd.cuda", pickB: "optimized", np: 1, ntomp: 1 })).toEqual({
      binary: "pmemd.cuda",
      ewald: "optimized",
      np: 1,
      ntomp: 1,
    })
  })
})
