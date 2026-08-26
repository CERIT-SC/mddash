import { describe, expect, it } from "vitest"

import { getAnalysisLabel } from "./analysis-utils"

describe("getAnalysisLabel", () => {
  it("labels base analyses from the catalog, by value or resultName", () => {
    expect(getAnalysisLabel("rmsds")).toBe("RMSD")
    expect(getAnalysisLabel("fluctuation")).toBe("RMSF (Fluctuation)")
  })

  it("labels numbered variants with the base label and the index", () => {
    expect(getAnalysisLabel("rmsd-pairwise-00")).toBe("Pairwise RMSD – 00")
  })

  it("falls back to title case for unknown names", () => {
    expect(getAnalysisLabel("mem-map")).toBe("Mem Map")
  })
})
