import { useState, useMemo } from "react";

import { Stack } from "@mui/material";

import { WizardStepProps } from "./Stepper";
import MolStar from "../MolStar";
import FileSelector from "../FileSelector";
import { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";
import { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates";

const STRUCTURE_FORMATS = ["pdb", "gro"];
const COORDINATE_FORMATS = ["xtc", "trr"];

const WizardAnalyze = (props: WizardStepProps) => {
    const { experiment, setErrorMessage } = props;

    const [structureFile, setStructureFile] = useState<string>("");
    const [coordsFile, setCoordsFile] = useState<string>("");

    const molstarViewer = useMemo(() => {
        if (!structureFile) return null;

        return (
            <MolStar
                width="800px"
                height="600px"
                structureUrl={structureFile}
                structureFormat={structureFile.split(".").pop() as BuiltInTrajectoryFormat}
                coordsUrl={coordsFile}
                coordsFormat={coordsFile.split(".").pop() as BuiltInCoordinatesFormat}
                setErrorMessage={setErrorMessage}
            />
        );
    }, [structureFile, coordsFile, setErrorMessage]);

    return (
        <Stack alignItems="center" spacing={2}>
            <FileSelector
                experimentId={experiment.id}
                ext={STRUCTURE_FORMATS}
                title="Select structure file"
                onFileSelected={setStructureFile}
                setErrorMessage={setErrorMessage}
            />
            <FileSelector
                experimentId={experiment.id}
                ext={COORDINATE_FORMATS}
                title="Select coordinates file"
                onFileSelected={setCoordsFile}
                setErrorMessage={setErrorMessage}
            />

            {molstarViewer}
        </Stack>
    );
};

export default WizardAnalyze;
