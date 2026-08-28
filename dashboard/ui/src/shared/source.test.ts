import { describe, expect, it } from "vitest"

import { sourceLabel, sourceTypeLabel } from "./source"

describe("sourceLabel", () => {
  it("returns null for unknown sources", () => {
    expect(sourceLabel(null)).toBeNull()
    expect(sourceLabel(undefined)).toBeNull()
  })

  it("labels PDB sources by accession, stripping the scheme for direct URLs", () => {
    expect(sourceLabel({ type: "pdb", pdb_id: "1LYZ", files: [] })).toBe("RCSB PDB (1LYZ)")
    expect(sourceLabel({ type: "pdb", url: "https://example.org/models/xyz.pdb", files: [] })).toBe(
      "example.org/models/xyz.pdb"
    )
    expect(sourceLabel({ type: "pdb", files: [] })).toBeNull()
  })

  it("labels repo sources by URL without the scheme", () => {
    expect(sourceLabel({ type: "repo", url: "https://doi.org/10.5281/zenodo.7261108", files: [] })).toBe(
      "10.5281/zenodo.7261108"
    )
    expect(sourceLabel({ type: "repo", url: "https://zenodo.org/records/7261108", files: [] })).toBe(
      "zenodo.org/records/7261108"
    )
    expect(sourceLabel({ type: "repo", url: "https://mdposit.mddash.eu/api/project/PP123", files: [] })).toBe(
      "mdposit.mddash.eu/api/project/PP123"
    )
  })

  it("labels upload sources by uploaded file count", () => {
    expect(sourceLabel({ type: "file", files: [{ name: "a.tpr", size: 1, path: "a.tpr", url: "/x" }] })).toBe(
      "Uploaded 1 file"
    )
    expect(
      sourceLabel({
        type: "file",
        files: [
          { name: "a.tpr", size: 1, path: "a.tpr", url: "/x" },
          { name: "b.pdb", size: 1, path: "b.pdb", url: "/y" },
        ],
      })
    ).toBe("Uploaded 2 files")
    expect(sourceLabel({ type: "file", files: [] })).toBeNull()
  })
})

describe("sourceTypeLabel", () => {
  it("classifies the source without claiming unearned provenance", () => {
    expect(sourceTypeLabel({ type: "pdb", pdb_id: "1LYZ", files: [] })).toBe("Protein Data Bank (RCSB)")
    expect(sourceTypeLabel({ type: "pdb", url: "https://example.org/x.pdb", files: [] })).toBe("PDB file (direct URL)")
    expect(sourceTypeLabel({ type: "repo", url: "https://zenodo.org/records/1", files: [] })).toBe(
      "External repository"
    )
    expect(sourceTypeLabel({ type: "file", files: [] })).toBe("File upload")
  })
})
