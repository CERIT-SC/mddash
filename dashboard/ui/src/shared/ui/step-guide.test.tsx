import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { StepGuide, type StepGuideStep } from "./step-guide"

function renderGuide(steps: StepGuideStep[]) {
  render(<StepGuide title="Step by step" label="Test guide" steps={steps} />)
  return screen.getByRole("region", { name: "Test guide" })
}

describe("StepGuide", () => {
  it("renders the panel as a labeled region with every step title", () => {
    const guide = renderGuide([
      { title: "First", state: "done" },
      { title: "Second", state: "active" },
      { title: "Third", state: "pending" },
    ])

    expect(guide).toHaveTextContent("Step by step")
    expect(guide).toHaveTextContent("First")
    expect(guide).toHaveTextContent("Second")
    expect(guide).toHaveTextContent("Third")
  })

  it("marks done steps, puts aria-current on the active one, and leaves pending bare", () => {
    renderGuide([
      { title: "First", state: "done" },
      { title: "Second", state: "active" },
      { title: "Third", state: "pending" },
    ])

    expect(screen.getAllByLabelText("Step 1 done")).toHaveLength(1)
    expect(screen.getByText("Second").closest("li")?.querySelector("[aria-current='step']")).toBeInTheDocument()
    expect(screen.getByText("Third").closest("li")?.querySelector("[aria-current='step']")).not.toBeInTheDocument()
  })

  it("drops the number and uses a check marker for done steps", () => {
    renderGuide([
      { title: "First", state: "done" },
      { title: "Second", state: "active" },
    ])

    expect(screen.queryByText("1")).not.toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("renders step bodies in place and supports several active steps", () => {
    const guide = renderGuide([
      { title: "First", state: "done" },
      { title: "Second", state: "active", body: <button type="button">Do second</button> },
      { title: "Third", state: "active", body: <p>Third note</p> },
    ])

    expect(screen.getByRole("button", { name: "Do second" })).toBeInTheDocument()
    expect(screen.getByText("Third note")).toBeInTheDocument()
    expect(guide.querySelectorAll("[aria-current='step']")).toHaveLength(2)
  })
})
