import { useState, useMemo, useEffect } from "react";

import { Stack, Paper, Box, Typography } from "@mui/material";
import { Category, Timeline } from "@mui/icons-material";
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

    useEffect(() => {
        // also clear coords file when structure file is cleared
        if (!structureFile) {
            setCoordsFile("");
        }
    }, [structureFile]);

    const molstarViewer = useMemo(() => {
        if (!structureFile) return null;

        return (
            <MolStar
                width="800px"
                height="600px"
                structureUrl={structureFile}
                structureFormat={structureFile.split(".").pop() as BuiltInTrajectoryFormat}
                coordsUrl={coordsFile || undefined}
                coordsFormat={coordsFile ? (coordsFile.split(".").pop() as BuiltInCoordinatesFormat) : undefined}
            />
        );
    }, [structureFile, coordsFile]);

    return (
        <Stack direction="column" alignItems="center" spacing={2}>
            <Stack direction="row" width="90%" spacing={2}>
                <Paper variant="outlined" sx={{ minWidth: 300, padding: 4 }}>
                    <Stack spacing={2}>
                        <Typography variant="h3">Analyze Files</Typography>

                        <Stack direction="row" spacing={1} alignItems="center">
                            <Category fontSize="small" color="action" />
                            <Typography variant="subtitle1" color="text.secondary">
                                Structure
                            </Typography>
                        </Stack>
                        <FileSelector
                            experimentId={experiment.id}
                            ext={STRUCTURE_FORMATS}
                            title="Select structure file"
                            onFileSelected={setStructureFile}
                        />
                        {structureFile && (
                            <>
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <Timeline fontSize="small" color="action" />
                                    <Typography variant="subtitle1" color="text.secondary">
                                        Coordinates
                                    </Typography>
                                </Stack>
                                <FileSelector
                                    experimentId={experiment.id}
                                    ext={COORDINATE_FORMATS}
                                    title="Select coordinates file"
                                    onFileSelected={setCoordsFile}
                                />
                            </>
                        )}
                    </Stack>
                </Paper>

                <Box flexGrow={1} display="flex" justifyContent="center" alignItems="center">
                    {molstarViewer}
                </Box>
            </Stack>
        </Stack>
    );
};

export default AnalyzeStep;
