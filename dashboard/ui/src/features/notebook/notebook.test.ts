import type { FileInfo, Notebook } from "@/api/generated/models"
import { describe, expect, it } from "vitest"

import { buildNotebookUrl, notebookRoleUrl, pickNotebookFile } from "./notebook"

function file(path: string): FileInfo {
  const name = path.split("/").pop() ?? path
  return { name, size: 1, path, url: `/files/${path}` }
}

const notebook: Notebook = {
  id: 1,
  experiment_id: "exp1",
  token: "tok",
  gpu: false,
  path: "/dash/notebook/exp1/?token=tok",
  status: "RUNNING",
  started_at: null,
}

describe("pickNotebookFile", () => {
  it("returns undefined without files", () => {
    expect(pickNotebookFile("setup", undefined)).toBeUndefined()
    expect(pickNotebookFile("setup", [])).toBeUndefined()
  })

  it("returns the sole canonical file, case-insensitively", () => {
    expect(pickNotebookFile("setup", [file("notes.md"), file("Setup.ipynb")])?.path).toBe("Setup.ipynb")
  })

  it("treats several canonical files as ambiguous", () => {
    const files = [file("z/setup.ipynb"), file("notes.md"), file("a/setup.ipynb")]
    expect(pickNotebookFile("setup", files)).toBeUndefined()
  })

  it("falls back to a lone notebook that is not the other role's", () => {
    expect(pickNotebookFile("setup", [file("workflow.ipynb")])?.path).toBe("workflow.ipynb")
    expect(pickNotebookFile("setup", [file("analysis.ipynb")])).toBeUndefined()
  })
})

describe("buildNotebookUrl", () => {
  it("drops the base query and encodes each path segment", () => {
    expect(buildNotebookUrl("/nb/exp1/?token=tok", "tok", "a dir/setup.ipynb")).toBe(
      "/nb/exp1/lab/tree/a%20dir/setup.ipynb?token=tok"
    )
  })
})

describe("notebookRoleUrl", () => {
  it("deep-links the role's file when found, else the plain token-embedded path", () => {
    expect(notebookRoleUrl("setup", [file("setup.ipynb")], notebook)).toBe(
      "/dash/notebook/exp1/lab/tree/setup.ipynb?token=tok"
    )
    expect(notebookRoleUrl("setup", [], notebook)).toBe("/dash/notebook/exp1/?token=tok")
    expect(notebookRoleUrl("setup", [file("a/setup.ipynb"), file("b/setup.ipynb")], notebook)).toBe(
      "/dash/notebook/exp1/?token=tok"
    )
    expect(notebookRoleUrl("setup", [file("setup.ipynb")], undefined)).toBeUndefined()
  })
})
