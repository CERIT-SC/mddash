import { Box, Button } from "@mui/material";

import { WizardStepperProps } from "./Stepper"

const WizardRun = (props: WizardStepperProps) => {
    console.log(props);

    return (
        <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Button variant="contained" color="primary">Run simulation</Button>
        </Box>
    );
};

export default WizardRun;
