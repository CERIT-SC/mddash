import { useState } from "react";

import { Box, Button, Typography } from "@mui/material";

import { WizardStepProps } from "./Stepper"
import FileSelector from "../FileSelector";

const WizardRun = (props: WizardStepProps) => {
    const { experiment, setErrorMessage } = props;
    const [tprFile, setTprFile] = useState<string | null>(null);

    return (
        <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <FileSelector experimentId={experiment.id} extension="tpr" onFileSelected={setTprFile} setErrorMessage={setErrorMessage} />
            <Typography variant="h5" sx={{ mt: 2 }}>
                Run simulation on {tprFile}
            </Typography>
            <Button variant="contained" color="primary">Run simulation</Button>
        </Box>
    );
};

export default WizardRun;
