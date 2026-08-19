// Locally-owned Stepper forked from the e-INFRA design system. Styled with DS
// tokens only so it reads as part of the design system, not alongside it.

import * as React from "react"

import { Button, cn } from "@e-infra/design-system"
import { ChevronLeft, ChevronRight } from "lucide-react"

interface Step {
  label: string
  description?: string
  icon?: React.ComponentType<{ className?: string }>
}

interface StepperContextValue {
  currentStep: number
  totalSteps: number
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: number) => void
}

const StepperContext = React.createContext<StepperContextValue | undefined>(undefined)

export function useStepper() {
  const context = React.useContext(StepperContext)
  if (!context) {
    throw new Error("useStepper must be used within a Stepper")
  }
  return context
}

interface StepperProps {
  children: React.ReactNode
  initialStep?: number
  step?: number
  totalSteps?: number
  onStepChange?: (step: number) => void
}

export function Stepper({
  children,
  initialStep = 0,
  step: stepProp,
  totalSteps: totalStepsProp,
  onStepChange,
}: StepperProps) {
  const clampStep = React.useCallback((step: number, stepsCount: number) => {
    const maxIndex = Math.max(stepsCount - 1, 0)
    return Math.max(0, Math.min(step, maxIndex))
  }, [])

  const isControlled = stepProp !== undefined
  const [internalStep, setInternalStep] = React.useState(initialStep)
  const steps = React.Children.toArray(children)
  const totalSteps = Math.max(totalStepsProp ?? steps.length, 1)
  const currentStep = clampStep(isControlled ? stepProp : internalStep, totalSteps)
  const previousInitialStepRef = React.useRef(initialStep)

  const changeStep = React.useCallback(
    (step: number) => {
      if (!isControlled) {
        setInternalStep(step)
      }
      onStepChange?.(step)
    },
    [isControlled, onStepChange]
  )

  const nextStep = React.useCallback(() => {
    changeStep(clampStep(currentStep + 1, totalSteps))
  }, [changeStep, clampStep, currentStep, totalSteps])

  const previousStep = React.useCallback(() => {
    changeStep(clampStep(currentStep - 1, totalSteps))
  }, [changeStep, clampStep, currentStep, totalSteps])

  const goToStep = React.useCallback(
    (step: number) => {
      changeStep(clampStep(step, totalSteps))
    },
    [changeStep, clampStep, totalSteps]
  )

  React.useEffect(() => {
    if (isControlled) {
      return
    }
    setInternalStep((prev) => {
      const clamped = clampStep(prev, totalSteps)
      return prev === clamped ? prev : clamped
    })
  }, [clampStep, isControlled, totalSteps])

  React.useEffect(() => {
    if (isControlled || previousInitialStepRef.current === initialStep) {
      return
    }

    previousInitialStepRef.current = initialStep
    setInternalStep(clampStep(initialStep, totalSteps))
  }, [clampStep, initialStep, isControlled, totalSteps])

  return (
    <StepperContext.Provider
      value={{
        currentStep,
        totalSteps,
        nextStep,
        previousStep,
        goToStep,
      }}
    >
      <div className="w-full">{children}</div>
    </StepperContext.Provider>
  )
}

interface StepperHeaderProps {
  steps?: Step[]
  className?: string
  showNavigation?: boolean
}

export function StepperHeader({ steps = [], className, showNavigation = true }: StepperHeaderProps) {
  const { currentStep, previousStep, nextStep, goToStep, totalSteps } = useStepper()
  const safeTotalSteps = Math.max(totalSteps, 1)
  const activeStepIndex = Math.min(Math.max(currentStep, 0), safeTotalSteps - 1)
  const progressPercentage = safeTotalSteps > 1 ? (activeStepIndex / (safeTotalSteps - 1)) * 100 : 100
  const isLastStep = activeStepIndex === safeTotalSteps - 1
  const stepMarkerSize = 28
  const stepItems = Array.from({ length: safeTotalSteps }, (_, index) => ({
    label: steps[index]?.label ?? `Step ${String(index + 1)}`,
    icon: steps[index]?.icon,
  }))
  const currentStepLabel = stepItems[activeStepIndex]?.label ?? `Step ${String(activeStepIndex + 1)}`

  return (
    <nav aria-label="Progress" className={cn("mb-8", className)}>
      <div className="flex w-full flex-col items-center gap-3">
        <p className="text-text text-center text-xs">
          <span className="font-normal">Section {activeStepIndex + 1}: </span>
          <span className="font-semibold">{currentStepLabel}</span>
        </p>
        <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          Section {activeStepIndex + 1} of {safeTotalSteps}: {currentStepLabel}
        </p>

        <div className="flex w-full items-center justify-center gap-4 md:gap-10">
          {showNavigation && (
            <div className="shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={previousStep}
                disabled={currentStep === 0}
                className="gap-1.5 md:min-w-26"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </Button>
            </div>
          )}

          {/* max-w-lg only balances against the flanking Previous/Next buttons */}
          <div className={cn("relative w-full", showNavigation && "max-w-lg")}>
            <div className="relative">
              <div className="bg-border/80 absolute top-1/2 right-3 left-3 h-2 -translate-y-1/2 rounded-full" />
              <div
                className="bg-primary absolute top-1/2 left-3 h-2 -translate-y-1/2 rounded-full transition-all"
                style={{
                  width: `calc(${String(progressPercentage)}% - ${String(progressPercentage / 100)} * ${String(stepMarkerSize)}px + ${String(isLastStep ? 0 : stepMarkerSize)}px)`,
                }}
              />

              <div className="relative flex items-center justify-between">
                {stepItems.map((step, index) => {
                  const isComplete = index < currentStep
                  const isCurrent = index === currentStep

                  return (
                    <button
                      key={`${step.label}-${String(index)}`}
                      type="button"
                      onClick={() => {
                        goToStep(index)
                      }}
                      aria-current={isCurrent ? "step" : undefined}
                      aria-label={`Go to section ${String(index + 1)}: ${step.label}`}
                      className={cn(
                        "relative z-10 flex cursor-pointer items-center justify-center rounded-full text-[14px] leading-5 font-semibold tracking-[0.07px] transition-all duration-300",
                        isComplete && "border-success bg-success text-success-foreground h-6 w-6 border-4",
                        isCurrent && "border-background bg-warning text-warning-foreground h-7 w-7 border-2",
                        !isComplete && !isCurrent && "border-background bg-border/80 text-text h-7 w-7 border-2"
                      )}
                      style={{
                        boxShadow: isComplete
                          ? "0 0 8px rgba(22, 154, 89, 0.65), 0 0 16px rgba(22, 154, 89, 0.35)"
                          : isCurrent
                            ? "0 0 8px rgba(247, 206, 91, 0.55), 0 0 14px rgba(247, 206, 91, 0.3)"
                            : "0 0 6px rgba(115, 112, 128, 0.38)",
                      }}
                    >
                      {step.icon ? <step.icon className="h-4 w-4" aria-hidden /> : index + 1}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {showNavigation && (
            <div className="shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={nextStep}
                disabled={currentStep === totalSteps - 1}
                className="gap-1.5 md:min-w-26"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
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

interface StepperFooterProps {
  children?: React.ReactNode
  className?: string
  showDefaultButtons?: boolean
  nextLabel?: string
  previousLabel?: string
  finishLabel?: string
  onFinish?: () => void
}

export function StepperFooter({
  children,
  className,
  showDefaultButtons = true,
  nextLabel = "Next",
  previousLabel = "Previous",
  finishLabel = "Finish",
  onFinish,
}: StepperFooterProps) {
  const { currentStep, totalSteps, nextStep, previousStep } = useStepper()
  const isFirstStep = currentStep === 0
  const isLastStep = currentStep === totalSteps - 1

  if (children) {
    return <div className={cn("mt-8 flex justify-between", className)}>{children}</div>
  }

  if (!showDefaultButtons) return null

  return (
    <div className={cn("mt-8 flex justify-between", className)}>
      <Button variant="outline" onClick={previousStep} disabled={isFirstStep}>
        {previousLabel}
      </Button>
      {isLastStep ? <Button onClick={onFinish}>{finishLabel}</Button> : <Button onClick={nextStep}>{nextLabel}</Button>}
    </div>
  )
}
