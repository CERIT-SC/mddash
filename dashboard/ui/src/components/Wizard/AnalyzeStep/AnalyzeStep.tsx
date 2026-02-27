import { useState, useMemo, useEffect } from "react";

import { Shapes, Activity } from "lucide-react";
import { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";
import { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import MolStar from "@/components/MolStar";
import FileSelector from "@/components/FileSelector";
import NotebookController from "@/components/Wizard/SetupStep/NotebookController";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STRUCTURE_FORMATS = ["pdb", "gro"];
const COORDINATE_FORMATS = ["xtc", "trr"];

const AnalyzeStep = (props: WizardStepProps) => {
    const { experiment } = props;

    const [structureFile, setStructureFile] = useState<string>("");
    const [coordsFile, setCoordsFile] = useState<string>("");

    useEffect(() => {
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
        <div className="flex flex-col items-center gap-4 w-full">
            <div className="flex flex-row gap-4 w-[90%] items-start">
                <div className="flex flex-col gap-4 min-w-72">
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base">Analyze Files</CardTitle>
                        </CardHeader>
                        <CardContent className="flex flex-col gap-4">
                            <div className="flex flex-col gap-2">
                                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                                    <Shapes className="h-4 w-4" />
                                    <span>Structure</span>
                                </div>
                                <FileSelector
                                    experimentId={experiment.id}
                                    ext={STRUCTURE_FORMATS}
                                    title="Select structure file"
                                    onFileSelected={setStructureFile}
                                />
                            </div>

                            {structureFile && (
                                <div className="flex flex-col gap-2">
                                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                                        <Activity className="h-4 w-4" />
                                        <span>Coordinates</span>
                                    </div>
                                    <FileSelector
                                        experimentId={experiment.id}
                                        ext={COORDINATE_FORMATS}
                                        title="Select coordinates file"
                                        onFileSelected={setCoordsFile}
                                    />
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <NotebookController experimentId={experiment.id} />
                </div>

                <div className="flex-1 flex justify-center items-center">{molstarViewer}</div>
            </div>
        </div>
    );
};

export default AnalyzeStep;
