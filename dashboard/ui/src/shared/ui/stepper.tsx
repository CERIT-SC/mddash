// Locally-owned Stepper forked from the e-INFRA design system. Styled with DS
// tokens only so it reads as part of the design system, not alongside it.

import * as React from "react"

import { cn } from "@e-infra/design-system"
import { Check } from "lucide-react"

interface Step {
  label: string
  description?: string
  icon?: React.ComponentType<{ className?: string }>
}

interface StepperContextValue {
  currentStep: number
  totalSteps: number
  goToStep: (step: number) => void
}

const StepperContext = React.createContext<StepperContextValue | undefined>(undefined)

function useStepper() {
  const context = React.useContext(StepperContext)
  if (!context) {
    throw new Error("useStepper must be used within a Stepper")
  }
  return context
}

interface StepperProps {
  children: React.ReactNode
  step: number
  totalSteps?: number
  onStepChange: (step: number) => void
}

export function Stepper({ children, step, totalSteps: totalStepsProp, onStepChange }: StepperProps) {
  const clampStep = React.useCallback((value: number, stepsCount: number) => {
    const maxIndex = Math.max(stepsCount - 1, 0)
    return Math.max(0, Math.min(value, maxIndex))
  }, [])

  const steps = React.Children.toArray(children)
  const totalSteps = Math.max(totalStepsProp ?? steps.length, 1)
  const currentStep = clampStep(step, totalSteps)

  const goToStep = React.useCallback(
    (value: number) => {
      onStepChange(clampStep(value, totalSteps))
    },
    [onStepChange, clampStep, totalSteps]
  )

  return (
    <StepperContext.Provider value={{ currentStep, totalSteps, goToStep }}>
      <div className="w-full">{children}</div>
    </StepperContext.Provider>
  )
}

interface StepperHeaderProps {
  steps?: Step[]
  className?: string
  /** Farthest clickable marker (server-reported progress); later ones render disabled. */
  maxStep?: number
  /** Extra markers clickable outside the maxStep threshold (e.g. experiment-level Publish). */
  unlockedIndexes?: readonly number[]
}

export function StepperHeader({ steps = [], className, maxStep, unlockedIndexes = [] }: StepperHeaderProps) {
  const { currentStep, goToStep, totalSteps } = useStepper()
  const safeTotalSteps = Math.max(totalSteps, 1)
  const activeStepIndex = Math.min(Math.max(currentStep, 0), safeTotalSteps - 1)
  const progressPercentage = safeTotalSteps > 1 ? (activeStepIndex / (safeTotalSteps - 1)) * 100 : 100
  const isLastStep = activeStepIndex === safeTotalSteps - 1
  const stepMarkerSize = 40
  const stepItems = Array.from({ length: safeTotalSteps }, (_, index) => ({
    label: steps[index]?.label ?? `Step ${String(index + 1)}`,
    icon: steps[index]?.icon,
  }))
  const currentStepLabel = stepItems[activeStepIndex]?.label ?? `Step ${String(activeStepIndex + 1)}`

  return (
    <nav aria-label="Progress" className={cn("mb-8", className)}>
      <div className="flex w-full flex-col items-center gap-3">
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          Section {activeStepIndex + 1} of {safeTotalSteps}: {currentStepLabel}
        </p>

        <div className="w-full">
          <div className="relative">
            {/* Track lines sit on the circle row's center: markers are h-10 (40px), so center is top-5. */}
            <div className="bg-border/80 absolute top-5 right-3 left-3 h-2 -translate-y-1/2 rounded-full" />
            <div
              className="bg-primary absolute top-5 left-3 h-2 -translate-y-1/2 rounded-full transition-all"
              style={{
                width: `calc(${String(progressPercentage)}% - ${String(progressPercentage / 100)} * ${String(stepMarkerSize)}px + ${String(isLastStep ? 0 : stepMarkerSize)}px)`,
              }}
            />

            <div className="relative flex items-start justify-between">
              {stepItems.map((step, index) => {
                const isComplete = index < currentStep
                const isCurrent = index === currentStep
                // maxStep opens a contiguous range; unlockedIndexes open specific
                // markers beyond it without freeing the ladder in between.
                const reachable = maxStep === undefined || index <= maxStep || unlockedIndexes.includes(index)

                return (
                  <button
                    key={`${step.label}-${String(index)}`}
                    type="button"
                    disabled={!reachable}
                    onClick={() => {
                      goToStep(index)
                    }}
                    aria-current={isCurrent ? "step" : undefined}
                    aria-label={`Go to section ${String(index + 1)}: ${step.label}`}
                    className={cn(
                      "relative z-10 flex flex-col items-center gap-1.5 first:items-start last:items-end",
                      reachable ? "cursor-pointer" : "cursor-not-allowed"
                    )}
                  >
                    {/* border-background punches the marker out of the track — the
                        markers sit on the wizard panel's bg-background. */}
                    <span
                      className={cn(
                        "flex items-center justify-center rounded-full text-[14px] leading-5 font-semibold tracking-[0.07px] transition-all duration-300",
                        isComplete &&
                          "border-success bg-success text-success-foreground shadow-success/50 h-9 w-9 border-4 shadow-[0_0_8px,0_0_16px]",
                        isCurrent &&
                          "border-background bg-warning text-warning-foreground shadow-warning/50 h-10 w-10 border-2 shadow-[0_0_8px,0_0_14px]",
                        !isComplete &&
                          !isCurrent &&
                          "border-background bg-border/80 text-text shadow-base-500/40 h-10 w-10 border-2 shadow-[0_0_6px]"
                      )}
                    >
                      {isComplete ? (
                        <Check className="h-5 w-5" aria-hidden />
                      ) : step.icon ? (
                        <step.icon className="h-6 w-6" aria-hidden />
                      ) : (
                        index + 1
                      )}
                    </span>
                    <span
                      className={cn(
                        "text-xs whitespace-nowrap",
                        isCurrent ? "text-text font-semibold" : "text-text-muted"
                      )}
                    >
                      {step.label}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </nav>
  )
}

interface StepperContentProps {
  children: React.ReactNode
  className?: string
}

export function StepperContent({ children, className }: StepperContentProps) {
  const { currentStep } = useStepper()
  const steps = React.Children.toArray(children)

  return <div className={cn("py-4", className)}>{steps[currentStep] || null}</div>
}
