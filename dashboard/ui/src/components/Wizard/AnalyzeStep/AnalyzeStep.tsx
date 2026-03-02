import { useEffect, useMemo, useState } from "react"

import { Activity, Shapes } from "lucide-react"
import { type BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates"
import { type BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory"

import type { FileOption } from "@/util/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"
import MolStar from "@/components/MolStar"
import NotebookController from "@/components/Wizard/SetupStep/NotebookController"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

const STRUCTURE_FORMATS = ["pdb", "gro"]
const COORDINATE_FORMATS = ["xtc", "trr"]

const AnalyzeStep = (props: WizardStepProps) => {
  const { experiment } = props

  const [structureFile, setStructureFile] = useState<FileOption | null>(null)
  const [coordsFile, setCoordsFile] = useState<FileOption | null>(null)

  useEffect(() => {
    if (!structureFile) {
      setCoordsFile(null)
    }
  }, [structureFile])

  const molstarViewer = useMemo(() => {
    if (!structureFile) return null

    return (
      <MolStar
        width="800px"
        height="600px"
        structureUrl={structureFile.url}
        structureFormat={structureFile.name.split(".").pop() as BuiltInTrajectoryFormat}
        coordsUrl={coordsFile?.url}
        coordsFormat={coordsFile ? (coordsFile.name.split(".").pop() as BuiltInCoordinatesFormat) : undefined}
      />
    )
  }, [structureFile, coordsFile])

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-[90%] flex-row items-start gap-4">
        <div className="flex min-w-72 flex-col gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Analyze Files</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <div className="text-muted-foreground flex items-center gap-1 text-sm">
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
                  <div className="text-muted-foreground flex items-center gap-1 text-sm">
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

        <div className="flex flex-1 items-center justify-center">{molstarViewer}</div>
      </div>
    </div>
  )
}

export default AnalyzeStep
