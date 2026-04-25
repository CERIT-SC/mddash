import type { AnalysisPreprocessingMode as AnalysisPreprocessingModeValue } from "@/util/analysis-types"
import type { FileOption } from "@/util/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"
import NotebookController from "@/components/NotebookController"

interface AnalyzeSidebarProps {
  experimentId: string
  structureExts: string[]
  trajectoryExts: string[]
  structureFile: FileOption | null
  topologyRequired: boolean
  topologyFormats: string[]
  topologyTitle: string
  preprocessingMode: AnalysisPreprocessingModeValue
  onStructureSelected: (file: FileOption | null) => void
  onCoordsSelected: (file: FileOption | null) => void
  onTopologySelected: (file: FileOption | null) => void
}

const AnalyzeSidebar = ({
  experimentId,
  structureExts,
  trajectoryExts,
  structureFile,
  topologyRequired,
  topologyFormats,
  topologyTitle,
  preprocessingMode,
  onStructureSelected,
  onCoordsSelected,
  onTopologySelected,
}: AnalyzeSidebarProps) => {
  return (
    <div className="flex w-72 shrink-0 flex-col gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Analysis Inputs</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <FileSelector
            experimentId={experimentId}
            ext={structureExts}
            title="Structure file"
            onFileSelected={onStructureSelected}
            className="w-full"
          />
          <FileSelector
            key={`coords-${structureFile?.path ?? "none"}`}
            experimentId={experimentId}
            ext={trajectoryExts}
            title="Trajectory file"
            onFileSelected={onCoordsSelected}
            className="w-full"
          />
          {topologyRequired && topologyFormats.length > 0 && (
            <FileSelector
              key={`topology-${preprocessingMode}-${topologyRequired ? "required" : "optional"}`}
              experimentId={experimentId}
              ext={topologyFormats}
              title={topologyTitle}
              onFileSelected={onTopologySelected}
              className="w-full"
            />
          )}
        </CardContent>
      </Card>

      <NotebookController experimentId={experimentId} className="w-full" compact />
    </div>
  )
}

export default AnalyzeSidebar
