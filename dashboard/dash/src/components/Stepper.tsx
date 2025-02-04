import { styled, Stepper, Step, StepLabel, StepIconProps, StepConnector, stepConnectorClasses } from '@mui/material';
import { BlurOn, Tune, PlayArrow, Assessment, Publish } from '@mui/icons-material';


const steps = [
    { label: 'Setup', icon: <BlurOn /> },
    { label: 'Tune', icon: <Tune /> },
    { label: 'Run', icon: <PlayArrow /> },
    { label: 'Analyze', icon: <Assessment /> },
    { label: 'Publish', icon: <Publish /> },
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
                'linear-gradient( 95deg,rgb(242,113,33) 0%,rgb(233,64,87) 50%,rgb(138,35,135) 100%)',
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
}>(({ theme }) => ({
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
    variants: [
        {
            props: ({ ownerState }) => ownerState.active,
            style: {
                backgroundImage:
                    'linear-gradient( 136deg, rgb(242,113,33) 0%, rgb(233,64,87) 50%, rgb(138,35,135) 100%)',
                boxShadow: '0 4px 10px 0 rgba(0,0,0,.25)',
            },
        },
        {
            props: ({ ownerState }) => ownerState.completed,
            style: {
                backgroundImage:
                    'linear-gradient( 136deg, rgb(242,113,33) 0%, rgb(233,64,87) 50%, rgb(138,35,135) 100%)',
            },
        },
    ],
}));


function ColorlibStepIcon(props: StepIconProps) {
    const { active, completed, className, icon } = props;
    const step = steps[Number(icon) - 1];

    return (
        <ColorlibStepIconRoot ownerState={{ completed, active }} className={className}>
            {step.icon}
        </ColorlibStepIconRoot>
    );
}


export default function CustomStepper() {
    return (
        <Stepper alternativeLabel activeStep={1} connector={<ColorlibConnector />}>
            {steps.map((step) => (
                <Step key={step.label}>
                    <StepLabel StepIconComponent={ColorlibStepIcon}>{step.label}</StepLabel>
                </Step>
            ))}
        </Stepper>
    );
}
