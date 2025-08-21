import React, { useState } from "react";
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

import WizardSetup from "./Setup";
import WizardTune from "./Tune";
import WizardRun from "./Run";
import WizardAnalyze from "./Analyze";
import WizardPublish from "./Publish";
import { Experiment } from "../../util/types";
import { DEBUG } from "../../util/const";

const steps = [
    { label: "Setup", icon: <BlurOn />, child: WizardSetup },
    { label: "Tune", icon: <Tune />, child: WizardTune },
    { label: "Run", icon: <PlayArrow />, child: WizardRun },
    { label: "Analyze", icon: <Assessment />, child: WizardAnalyze },
    { label: "Publish", icon: <Publish />, child: WizardPublish },
];

const ColorLibConnector = styled(StepConnector)(({ theme }) => ({
    [`&.${stepConnectorClasses.alternativeLabel}`]: {
        top: 22,
    },
    [`&.${stepConnectorClasses.active}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundImage: "linear-gradient( 95deg,rgb(242,113,33) 0%,rgb(233,64,87) 50%,rgb(138,35,135) 100%)",
        },
    },
    [`&.${stepConnectorClasses.completed}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundImage: "linear-gradient( 95deg,rgb(0,200,83) 0%,rgb(0,150,136) 50%,rgb(0,100,83) 100%)",
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
        ...theme.applyStyles("dark", {
            backgroundColor: theme.palette.grey[700],
        }),
        ...(ownerState.active && {
            backgroundImage: "linear-gradient( 136deg, rgb(242,113,33) 0%, rgb(233,64,87) 50%, rgb(138,35,135) 100%)",
            boxShadow: "0 4px 10px 0 rgba(0,0,0,.25)",
        }),
        ...(ownerState.completed && {
            backgroundImage: "linear-gradient( 136deg, rgb(0,200,83) 0%, rgb(0,150,136) 50%, rgb(0,100,83) 100%)",
        }),
    })
);

export interface WizardStepperProps {
    experiment: Experiment;
    setExperiment: Function;
    setErrorMessage: (message: string) => void;
}

export interface WizardStepProps extends WizardStepperProps {
    nextStep: () => void;
    changeStep: (step: number) => void;
}

const WizardStepper = (props: WizardStepperProps) => {
    const { experiment, setExperiment } = props;
    const [activeStep, setActiveStep] = useState(Math.min(experiment.step || 0, steps.length - 1));

    const changeStep = async (step: number) => {
        if (step < 0 || step >= steps.length) return;
        if (step > (experiment.step || 0)) return;

        setActiveStep(step);
    };

    const nextStep = () => {
        if ((experiment.step || 0) >= steps.length - 1) return;

        setActiveStep((experiment.step || 0) + 1);
        setExperiment((prev: Experiment) => {
            return { ...prev, step: (prev.step || 0) + 1 };
        });
    };

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
                    <Step key={step.label} completed={idx < (experiment.step || 0)}>
                        <StepLabel StepIconComponent={ColorLibStepIcon}>{step.label}</StepLabel>
                    </Step>
                ))}
            </Stepper>

            <Box sx={{ mt: 4 }}>
                {React.createElement(steps[activeStep].child, childProps)}
            </Box>
        </>
    );
};

export default WizardStepper;
