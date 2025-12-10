import React, { useState, useEffect, useCallback } from "react";

import {
    styled,
    Stepper,
    Step,
    StepLabel,
    StepIconProps,
    StepConnector,
    stepConnectorClasses,
    Box,
    Button,
} from "@mui/material";
import { BlurOn, Tune, PlayArrow, Assessment, Publish } from "@mui/icons-material";

import { Experiment } from "@/util/types";
import { DEBUG } from "@/util/const";
import { get_experiment_step } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import WizardSetup from "./SetupStep";
import TuneStep from "./TuneStep";
import RunStep from "./RunStep";
import AnalyzeStep from "./AnalyzeStep";
import PublishStep from "./PublishStep";

const steps = [
    { label: "Setup", icon: <BlurOn />, child: WizardSetup },
    { label: "Tune", icon: <Tune />, child: TuneStep },
    { label: "Run", icon: <PlayArrow />, child: RunStep },
    { label: "Analyze", icon: <Assessment />, child: AnalyzeStep },
    { label: "Publish", icon: <Publish />, child: PublishStep },
];

const ColorLibConnector = styled(StepConnector)(({ theme }) => ({
    [`&.${stepConnectorClasses.alternativeLabel}`]: {
        top: 22,
    },
    [`&.${stepConnectorClasses.active}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundColor: theme.palette.primary.main,
        },
    },
    [`&.${stepConnectorClasses.completed}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundColor: theme.palette.success.main,
        },
    },
    [`& .${stepConnectorClasses.line}`]: {
        height: 3,
        border: 0,
        backgroundColor: "#eaeaf0",
        borderRadius: 1,
        ...theme.applyStyles("dark", {
            backgroundColor: theme.palette.grey[800],
        }),
    },
}));

const ColorLibStepIconRoot = styled("div")<{ ownerState: { completed?: boolean; active?: boolean } }>(
    ({ theme, ownerState }) => ({
        backgroundColor: "#ccc",
        zIndex: 1,
        color: "#fff",
        width: 50,
        height: 50,
        display: "flex",
        borderRadius: "50%",
        justifyContent: "center",
        alignItems: "center",
        cursor: "pointer",
        transition: "transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out",
        "&:hover": {
            transform: "scale(1.1)",
            boxShadow: "0 4px 12px 0 rgba(0,0,0,.3)",
        },
        ...theme.applyStyles("dark", {
            backgroundColor: theme.palette.grey[700],
        }),
        ...(ownerState.active && {
            backgroundColor: theme.palette.primary.main,
            boxShadow: "0 4px 10px 0 rgba(0,0,0,.25)",
        }),
        ...(ownerState.completed && {
            backgroundColor: theme.palette.success.main,
        }),
    }),
);

export interface WizardStepperProps {
    experiment: Experiment;
    setExperiment: React.Dispatch<React.SetStateAction<Experiment | null>>;
}

export interface WizardStepProps extends WizardStepperProps {
    nextStep: () => void;
    changeStep: (step: number) => void;
}

const WizardStepper = (props: WizardStepperProps) => {
    const { experiment, setExperiment } = props;
    const { showError } = useNotification();
    const [activeStep, setActiveStep] = useState(Math.min(experiment.step, steps.length - 1));

    const fetchStep = useCallback(async () => {
        const { data, error } = await get_experiment_step(experiment.id);

        if (error) showError(error);
        else if (data !== null && data !== experiment.step) {
            setExperiment((prev) => {
                if (!prev) return prev;
                return { ...prev, step: data };
            });
        }
    }, [experiment.id, experiment.step, setExperiment, showError]);

    const changeStep = async (step: number) => {
        if (step < 0 || step >= steps.length) return;
        if (step > experiment.step) return; // can only go forward using nextStep
        setActiveStep(step);
    };

    const nextStep = () => {
        if (experiment.step >= steps.length - 1) return;

        setActiveStep(experiment.step + 1);
        setExperiment((prev) => {
            if (!prev) return prev;
            return { ...prev, step: prev.step + 1 };
        });
    };

    useEffect(() => {
        const interval = setInterval(fetchStep, 5000);
        return () => clearInterval(interval);
    }, [experiment.id, experiment.step, fetchStep]);

    const childProps = {
        ...props,
        nextStep: nextStep,
        changeStep: changeStep,
    };

    const ColorLibStepIcon = (props: StepIconProps) => {
        const { active, completed, className, icon } = props;
        const idx = Number(icon) - 1;
        const step = steps[idx];

        return (
            <ColorLibStepIconRoot
                ownerState={{ completed, active }}
                className={className}
                onClick={() => changeStep(idx)}
            >
                {step.icon}
            </ColorLibStepIconRoot>
        );
    };

    return (
        <>
            {DEBUG && (
                <Button variant="contained" onClick={() => nextStep()}>
                    DEBUG: next step
                </Button>
            )}

            <Stepper alternativeLabel activeStep={activeStep} connector={<ColorLibConnector />}>
                {steps.map((step, idx) => (
                    <Step key={step.label} completed={idx < experiment.step || idx < activeStep}>
                        <StepLabel StepIconComponent={ColorLibStepIcon}>{step.label}</StepLabel>
                    </Step>
                ))}
            </Stepper>

            <Box sx={{ mt: 4 }}>{React.createElement(steps[activeStep].child, childProps)}</Box>
        </>
    );
};

export default WizardStepper;
