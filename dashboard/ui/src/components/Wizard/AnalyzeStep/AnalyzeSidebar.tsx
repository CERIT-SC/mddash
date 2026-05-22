import type { FileOption } from "@/util/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"
import NotebookController from "@/components/NotebookController"

interface AnalyzeSidebarProps {
  experimentId: string
  structureExts: string[]
  trajectoryExts: string[]
  structureFile: FileOption | null
  coordsFile: FileOption | null
  topologyFile: FileOption | null
  topologyRequired: boolean
  topologyFormats: string[]
  topologyTitle: string
  onStructureSelected: (file: FileOption | null) => void
  onCoordsSelected: (file: FileOption | null) => void
  onTopologySelected: (file: FileOption | null) => void
}

const AnalyzeSidebar = ({
  experimentId,
  structureExts,
  trajectoryExts,
  structureFile,
  coordsFile,
  topologyFile,
  topologyRequired,
  topologyFormats,
  topologyTitle,
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
            selectedPath={structureFile?.path ?? null}
            onFileSelected={onStructureSelected}
            className="w-full"
          />
          <FileSelector
            experimentId={experimentId}
            ext={trajectoryExts}
            title="Trajectory file"
            selectedPath={coordsFile?.path ?? null}
            onFileSelected={onCoordsSelected}
            className="w-full"
          />
          {topologyRequired && topologyFormats.length > 0 && (
            <FileSelector
              experimentId={experimentId}
              ext={topologyFormats}
              title={topologyTitle}
              selectedPath={topologyFile?.path ?? null}
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
