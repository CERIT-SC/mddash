import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Stepper, StepperContent, StepperHeader, type Step } from "./stepper"

function renderHeader(steps: Step[]) {
  return render(
    <Stepper step={0} totalSteps={steps.length} onStepChange={() => undefined}>
      <StepperHeader steps={steps} />
      <StepperContent>
        {steps.map((step) => (
          <div key={step.label} />
        ))}
      </StepperContent>
    </Stepper>
  )
}

const steps: Step[] = [{ label: "Setup" }, { label: "Tune" }, { label: "Run" }]

describe("StepperHeader progress", () => {
  it("shows the ring and percent for a step with progress", () => {
    const withProgress = steps.map((step, index) => (index === 2 ? { ...step, progress: 20 } : step))
    renderHeader(withProgress)
    const run = screen.getByRole("button", { name: "Go to section 3: Run, 20% complete" })
    expect(run.querySelector("svg")).not.toBeNull()
    expect(run).toHaveTextContent("Run · 20%")
  })

  it.each([null, undefined])("renders a plain marker when progress is %s", (progress) => {
    renderHeader(steps.map((step, index) => (index === 2 ? { ...step, progress } : step)))
    const run = screen.getByRole("button", { name: "Go to section 3: Run" })
    expect(run.querySelector("svg")).toBeNull()
    expect(run).toHaveTextContent("Run")
  })

  it("keeps the step icon instead of the complete check while in progress", () => {
    const withProgress = steps.map((step, index) => (index === 0 ? { ...step, progress: 50 } : step))
    render(
      <Stepper step={1} totalSteps={steps.length} onStepChange={() => undefined}>
        <StepperHeader steps={withProgress} />
        <StepperContent>
          {steps.map((step) => (
            <div key={step.label} />
          ))}
        </StepperContent>
      </Stepper>
    )
    const setup = screen.getByRole("button", { name: "Go to section 1: Setup, 50% complete" })
    expect(setup.querySelector("svg.lucide-check")).toBeNull()
  })
})
