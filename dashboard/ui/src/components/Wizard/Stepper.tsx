import React, { useState } from "react";

import { Atom, SlidersHorizontal, Play, BarChart2, Upload } from "lucide-react";

import { Experiment } from "@/util/types";
import { DEBUG } from "@/util/const";
import { useExperimentStep } from "@/hooks/use-experiment";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import WizardSetup from "./SetupStep";
import TuneStep from "./TuneStep";
import RunStep from "./RunStep";
import AnalyzeStep from "./AnalyzeStep";
import PublishStep from "./PublishStep";

const STEP_ICONS = [Atom, SlidersHorizontal, Play, BarChart2, Upload];
const STEP_LABELS = ["Setup", "Tune", "Run", "Analyze", "Publish"];
const STEP_COMPONENTS = [WizardSetup, TuneStep, RunStep, AnalyzeStep, PublishStep];

export interface WizardStepperProps {
    experiment: Experiment;
}

export interface WizardStepProps {
    experiment: Experiment;
    nextStep: () => void;
    changeStep: (step: number) => void;
}

const WizardStepper = ({ experiment }: WizardStepperProps) => {
    const queryClient = useQueryClient();
    const [activeStep, setActiveStep] = useState(Math.min(experiment.step, STEP_LABELS.length - 1));

    // Poll experiment step; hook updates experiment cache when step changes
    useExperimentStep(experiment.id, experiment.step);

    const changeStep = (step: number) => {
        if (step < 0 || step >= STEP_LABELS.length) return;
        if (step > experiment.step) return; // can only go forward using nextStep
        setActiveStep(step);
    };

    const nextStep = () => {
        if (experiment.step >= STEP_LABELS.length - 1) return;
        const newStep = experiment.step + 1;
        setActiveStep(newStep);
        queryClient.setQueryData<Experiment>(["experiment", experiment.id], (old) =>
            old ? { ...old, step: newStep } : old,
        );
    };

    const ActiveComponent = STEP_COMPONENTS[activeStep];

    return (
        <div className="flex flex-col gap-6">
            {DEBUG && (
                <Button variant="default" onClick={nextStep}>
                    DEBUG: next step
                </Button>
            )}

            {/* Custom stepper */}
            <div className="flex items-center justify-center">
                {STEP_LABELS.map((label, idx) => {
                    const Icon = STEP_ICONS[idx];
                    const isCompleted = idx < experiment.step || idx < activeStep;
                    const isActive = idx === activeStep;
                    const isClickable = idx <= experiment.step;

                    return (
                        <React.Fragment key={label}>
                            <div className="flex flex-col items-center gap-1">
                                <button
                                    type="button"
                                    disabled={!isClickable}
                                    onClick={() => changeStep(idx)}
                                    className={cn(
                                        "flex h-12 w-12 items-center justify-center rounded-full border-2 text-white transition-all",
                                        isActive && "bg-primary border-primary shadow-md scale-110",
                                        isCompleted && !isActive && "bg-green-500 border-green-500",
                                        !isActive && !isCompleted && "bg-muted border-border text-muted-foreground",
                                        isClickable &&
                                            !isActive &&
                                            !isCompleted &&
                                            "hover:scale-105 hover:shadow cursor-pointer",
                                        isClickable && isCompleted && "hover:scale-105 cursor-pointer",
                                    )}
                                >
                                    <Icon className="h-5 w-5" />
                                </button>
                                <span
                                    className={cn(
                                        "text-xs font-medium",
                                        isActive ? "text-primary" : "text-muted-foreground",
                                    )}
                                >
                                    {label}
                                </span>
                            </div>

                            {idx < STEP_LABELS.length - 1 && (
                                <div
                                    className={cn(
                                        "h-0.5 flex-1 mx-1 mb-5 transition-colors",
                                        idx < activeStep || idx < experiment.step
                                            ? "bg-green-500"
                                            : idx === activeStep
                                              ? "bg-primary"
                                              : "bg-border",
                                    )}
                                />
                            )}
                        </React.Fragment>
                    );
                })}
            </div>

            <div className="mt-2">
                <ActiveComponent experiment={experiment} nextStep={nextStep} changeStep={changeStep} />
            </div>
        </div>
    );
};

export default WizardStepper;
