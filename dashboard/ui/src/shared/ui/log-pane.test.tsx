import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { LogPane } from "./log-pane"

function lineDivs(container: HTMLElement) {
  return Array.from(container.firstElementChild?.children ?? [])
}

describe("LogPane", () => {
  it("renders one row per line", () => {
    const { container } = render(<LogPane logs={"alpha\nbeta"} />)
    const rows = lineDivs(container)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent("alpha")
    expect(rows[1]).toHaveTextContent("beta")
  })

  it("keeps DOM nodes for unchanged lines when appending live output", () => {
    const { container, rerender } = render(<LogPane logs={"a\nb"} />)
    const before = lineDivs(container)
    rerender(<LogPane logs={"a\nb\nc"} />)
    const after = lineDivs(container)
    expect(after).toHaveLength(3)
    expect(after[0]).toBe(before[0])
    expect(after[1]).toBe(before[1])
  })

  it("shows the error, loading, and empty states instead of content", () => {
    const { rerender, container } = render(<LogPane logs="x" errorText="gone" />)
    expect(container).toHaveTextContent("gone")

    rerender(<LogPane logs="x" isLoading />)
    expect(container).toHaveTextContent("waiting for output...")

    rerender(<LogPane logs="  " emptyText="nothing yet" />)
    expect(container).toHaveTextContent("nothing yet")
  })
})
