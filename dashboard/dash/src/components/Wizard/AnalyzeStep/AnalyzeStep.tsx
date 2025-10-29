import { useState, useMemo } from "react";

import { Stack } from "@mui/material";
import { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";
import { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import MolStar from "@/components/MolStar";
import FileSelector from "@/components/FileSelector";

const STRUCTURE_FORMATS = ["pdb", "gro"];
const COORDINATE_FORMATS = ["xtc", "trr"];

const AnalyzeStep = (props: WizardStepProps) => {
    const { experiment } = props;

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
            />
        );
    }, [structureFile, coordsFile]);

    return (
        <Stack alignItems="center" spacing={2}>
            <FileSelector
                experimentId={experiment.id}
                ext={STRUCTURE_FORMATS}
                title="Select structure file"
                onFileSelected={setStructureFile}
            />
            <FileSelector
                experimentId={experiment.id}
                ext={COORDINATE_FORMATS}
                title="Select coordinates file"
                onFileSelected={setCoordsFile}
            />

            {molstarViewer}
        </Stack>
    );
};

export default AnalyzeStep;
