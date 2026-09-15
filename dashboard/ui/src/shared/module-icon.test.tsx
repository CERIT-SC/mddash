import type { NotebookModuleCategory } from "@/api/generated/models"
import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ModuleIcon } from "./module-icon"

describe("ModuleIcon", () => {
  it("renders a known category", () => {
    const { container } = render(<ModuleIcon category="nucleic-acids" />)
    expect(container.querySelector("svg")).not.toBeNull()
  })

  it("falls back instead of crashing on a category this build does not know", () => {
    // the API's category set can outlive this build (new catalog entries, old snapshots)
    const { container } = render(<ModuleIcon category={"superfluid" as NotebookModuleCategory} />)
    expect(container.querySelector("svg")).not.toBeNull()
  })
})
