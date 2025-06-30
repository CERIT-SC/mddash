import { useState } from "react";

import { Stack } from "@mui/material";

import { WizardStepProps } from "./Stepper";
import MolStar from "../MolStar";
import FileSelector from "../FileSelector";

const WizardAnalyze = (props: WizardStepProps) => {
    const { experiment, setErrorMessage } = props;

    const [structureFile, setStructureFile] = useState<string>("");
    const [trajectoryFile, setTrajectoryFile] = useState<string>("");

    const structureType = "pdb";
    const trajectoryType = "xtc";

    return (
        <Stack alignItems="center" spacing={2}>
            <FileSelector
                experimentId={experiment.id}
                extension={structureType}
                onFileSelected={setStructureFile}
                setErrorMessage={setErrorMessage}
            />
            <FileSelector
                experimentId={experiment.id}
                extension={trajectoryType}
                onFileSelected={setTrajectoryFile}
                setErrorMessage={setErrorMessage}
            />

            {structureFile && (
                <MolStar
                    width="800px"
                    height="600px"
                    structureUrl={structureFile}
                    structureFormat={structureType}
                    trajectoryUrl={trajectoryFile}
                    trajectoryFormat={trajectoryType}
                    setErrorMessage={setErrorMessage}
                />
            )}
        </Stack>
    );
};

export default WizardAnalyze;
