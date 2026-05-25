import { useState } from "react"

import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"

import JobSelectorList from "./JobSelectorList"

interface TprSelectorProps {
  experimentId: string
  title?: string
  addTitle: string
  tprFiles: string[]
  selectedTpr: string | null
  loading?: boolean
  onAddTpr: (tpr: string) => void
  onDeleteTpr: (tpr: string) => void
  onSelectTpr: (tpr: string | null) => void
}

const TprSelector = (props: TprSelectorProps) => {
  const { experimentId, title, addTitle, tprFiles, selectedTpr, loading, onAddTpr, onDeleteTpr, onSelectTpr } = props

  const [fileSelectorTpr, setFileSelectorTpr] = useState<string>("")

  return (
    <Card className="w-72 shrink-0">
      <CardHeader className="pb-2">{title && <CardTitle className="text-base">{title}</CardTitle>}</CardHeader>
      <CardContent className="flex flex-col gap-3">
        <FileSelector
          experimentId={experimentId}
          ext="tpr"
          title="Select TPR file"
          selectedPath={fileSelectorTpr || null}
          onFileSelected={(file) => setFileSelectorTpr(file?.path ?? "")}
          ignoreFiles={tprFiles}
        />
        <Button
          variant="default"
          disabled={!fileSelectorTpr || tprFiles.includes(fileSelectorTpr)}
          onClick={() => {
            onAddTpr(fileSelectorTpr)
            setFileSelectorTpr("")
          }}
        >
          <Plus className="mr-1 h-4 w-4" />
          {addTitle}
        </Button>

        <JobSelectorList
          files={tprFiles}
          selectedFile={selectedTpr}
          loading={loading}
          onSelect={onSelectTpr}
          onDelete={onDeleteTpr}
        />
      </CardContent>
    </Card>
  )
}

export default TprSelector
