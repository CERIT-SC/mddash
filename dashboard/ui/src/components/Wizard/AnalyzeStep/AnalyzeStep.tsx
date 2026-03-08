import { useEffect, useMemo, useState } from "react"

import { Activity, Shapes } from "lucide-react"
import { type BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates"
import { type BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory"

import type { FileOption } from "@/util/types"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import FileSelector from "@/components/FileSelector"
import MolStar from "@/components/MolStar"
import NotebookController from "@/components/Wizard/SetupStep/NotebookController"
import { type WizardStepProps } from "@/components/Wizard/Stepper"

import AnalysisPanel from "./AnalysisPanel"

const STRUCTURE_FORMATS = ["pdb", "gro"]
const COORDINATE_FORMATS = ["xtc", "trr"]

const AnalyzeStep = (props: WizardStepProps) => {
  const { experiment } = props

  const [structureFile, setStructureFile] = useState<FileOption | null>(null)
  const [coordsFile, setCoordsFile] = useState<FileOption | null>(null)
  useEffect(() => {
    if (!structureFile) setCoordsFile(null)
  }, [structureFile])

  const molstarViewer = useMemo(() => {
    if (!structureFile) return null
    return (
      <MolStar
        width="100%"
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
      <div className="w-[90%]">
        <Tabs defaultValue="viewer">
          <TabsList>
            <TabsTrigger value="viewer">Structure Viewer</TabsTrigger>
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
            <TabsTrigger value="notebook">Notebook</TabsTrigger>
          </TabsList>

          <TabsContent value="viewer" className="mt-3 flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5">
                <Shapes className="text-muted-foreground h-4 w-4 shrink-0" />
                <FileSelector
                  experimentId={experiment.id}
                  ext={STRUCTURE_FORMATS}
                  title="Select structure file"
                  onFileSelected={setStructureFile}
                  className="w-52"
                />
              </div>
              {structureFile && (
                <div className="flex items-center gap-1.5">
                  <Activity className="text-muted-foreground h-4 w-4 shrink-0" />
                  <FileSelector
                    experimentId={experiment.id}
                    ext={COORDINATE_FORMATS}
                    title="Select trajectory file"
                    onFileSelected={setCoordsFile}
                    className="w-52"
                  />
                </div>
              )}
            </div>
            <div className="flex items-center justify-center">
              {molstarViewer ?? (
                <div className="border-muted-foreground/25 bg-muted text-muted-foreground flex h-150 w-full items-center justify-center rounded-lg border-2 border-dashed text-sm">
                  Select a structure file to view.
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="analysis" className="mt-3">
            <AnalysisPanel experimentId={experiment.id} />
          </TabsContent>

          <TabsContent value="notebook" className="mt-3">
            <NotebookController experimentId={experiment.id} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default AnalyzeStep
