import { useState } from "react";
import { styled, Stepper, Step, StepLabel, StepIconProps, StepConnector, stepConnectorClasses, Box, Button } from '@mui/material';
import { BlurOn, Tune, PlayArrow, Assessment, Publish } from '@mui/icons-material';

import WizardSetup from "./Setup";
import WizardTune from "./Tune";
import WizardRun from "./Run";
import WizardAnalyze from "./Analyze";
import WizardPublish from "./Publish";
import { Experiment } from "../../util/types";

const steps = [
    { label: 'Setup', icon: <BlurOn />, child: WizardSetup },
    { label: 'Tune', icon: <Tune />, child: WizardTune },
    { label: 'Run', icon: <PlayArrow />, child: WizardRun },
    { label: 'Analyze', icon: <Assessment />, child: WizardAnalyze },
    { label: 'Publish', icon: <Publish />, child: WizardPublish },
];

const ColorlibConnector = styled(StepConnector)(({ theme }) => ({
    [`&.${stepConnectorClasses.alternativeLabel}`]: {
        top: 22,
    },
    [`&.${stepConnectorClasses.active}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundImage:
                'linear-gradient( 95deg,rgb(242,113,33) 0%,rgb(233,64,87) 50%,rgb(138,35,135) 100%)',
        },
    },
    [`&.${stepConnectorClasses.completed}`]: {
        [`& .${stepConnectorClasses.line}`]: {
            backgroundImage:
                'linear-gradient( 95deg,rgb(0,200,83) 0%,rgb(0,150,136) 50%,rgb(0,100,83) 100%)',
        },
    },
    [`& .${stepConnectorClasses.line}`]: {
        height: 3,
        border: 0,
        backgroundColor: '#eaeaf0',
        borderRadius: 1,
        ...theme.applyStyles('dark', {
            backgroundColor: theme.palette.grey[800],
        }),
    },
}));

const ColorlibStepIconRoot = styled('div')<{
    ownerState: { completed?: boolean; active?: boolean };
}>(({ theme, ownerState }) => ({
    backgroundColor: '#ccc',
    zIndex: 1,
    color: '#fff',
    width: 50,
    height: 50,
    display: 'flex',
    borderRadius: '50%',
    justifyContent: 'center',
    alignItems: 'center',
    ...theme.applyStyles('dark', {
        backgroundColor: theme.palette.grey[700],
    }),
    ...(ownerState.active && {
        backgroundImage:
            'linear-gradient( 136deg, rgb(242,113,33) 0%, rgb(233,64,87) 50%, rgb(138,35,135) 100%)',
        boxShadow: '0 4px 10px 0 rgba(0,0,0,.25)',
    }),
    ...(ownerState.completed && {
        backgroundImage:
            'linear-gradient( 136deg, rgb(0,200,83) 0%, rgb(0,150,136) 50%, rgb(0,100,83) 100%)',
    }),
}));


export interface WizardStepperProps {
    experiment: Experiment;
    setExperiment: Function;
}

export default function WizardStepper(props: WizardStepperProps) {
    const { experiment, setExperiment } = props;
    const [activeStep, setActiveStep] = useState(experiment.step);


    const changeStep = async (step: number) => {
        if (step < 0 || step >= steps.length) return;
        if (step > experiment.step) return;

        setActiveStep(step);
    }

    const nextStep = () => {
        if (experiment.step >= steps.length - 1) return;

        setActiveStep(experiment.step + 1);
        setExperiment((prev: Experiment) => {return { ...prev, step: prev.step + 1 }});
    }


    const ColorlibStepIcon = (props: StepIconProps) => {
        const { active, completed, className, icon } = props;
        const idx = Number(icon) - 1;
        const step = steps[idx];
    
        return (
            <ColorlibStepIconRoot ownerState={{ completed, active }} className={className} onClick={() => changeStep(idx)}>
                {step.icon}
            </ColorlibStepIconRoot>
        );
    }

    return (
        <>
            <Button variant="contained" onClick={() => nextStep()}>DEBUG: next step</Button>

            <Stepper alternativeLabel activeStep={activeStep} connector={<ColorlibConnector />}>
                {steps.map((step, idx) => (
                    <Step key={step.label} completed={idx < experiment.step}>
                        <StepLabel StepIconComponent={ColorlibStepIcon}>{step.label}</StepLabel>
                    </Step>
                ))}
            </Stepper>
            
            <Box sx={{ mt: 4 }} >
                { steps[activeStep].child(props) }
            </Box>
        </>
    );
}
