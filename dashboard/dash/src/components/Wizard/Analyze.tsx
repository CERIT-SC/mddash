import { useState, useEffect } from "react";

import { Stack, CircularProgress } from "@mui/material";

import { WizardStepProps } from "./Stepper";
import MolStar from "../MolStar";


const WizardAnalyze = (props: WizardStepProps) => {
    console.log(props);

    const [molstarComponent, setMolstarComponent] = useState<JSX.Element | null>(null);

    useEffect(() => {
        const molstar = <MolStar width="800px" height="600px" pdbId="4A8B" />;
        setMolstarComponent(molstar);
    }, []);

    return (
        <Stack alignItems="center">
            {!molstarComponent ? (
                <CircularProgress />
            ) : (
                molstarComponent
            )}
        </Stack>
    );
};


export default WizardAnalyze;
