import { useState } from "react"

import { Plus } from "lucide-react"

import type { FileOption } from "@/util/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import FileSelector from "@/components/FileSelector"

import JobSelectorList from "./JobSelectorList"

export interface AmberJobEntry {
  prmtopName: string
  inpcrdName: string
  mdinName: string
}

interface AmberSelectorProps {
  experimentId: string
  jobs: string[]
  selectedPrmtop: string | null
  loading?: boolean
  onAddJob: (entry: AmberJobEntry) => void
  onDeleteJob: (prmtopName: string) => void
  onSelectJob: (prmtopName: string | null) => void
}

const AmberSelector = (props: AmberSelectorProps) => {
  const { experimentId, jobs, selectedPrmtop, loading, onAddJob, onDeleteJob, onSelectJob } = props

  const [selectorKey, setSelectorKey] = useState(0)
  const [prmtopFile, setPrmtopFile] = useState<FileOption | null>(null)
  const [inpcrdFile, setInpcrdFile] = useState<FileOption | null>(null)
  const [mdinFile, setMdinFile] = useState<FileOption | null>(null)

  const canAdd = !!(prmtopFile && inpcrdFile && mdinFile) && !jobs.includes(prmtopFile.path)

  const handleAdd = () => {
    if (!prmtopFile || !inpcrdFile || !mdinFile) return
    onAddJob({ prmtopName: prmtopFile.path, inpcrdName: inpcrdFile.path, mdinName: mdinFile.path })
    setPrmtopFile(null)
    setInpcrdFile(null)
    setMdinFile(null)
    setSelectorKey((k) => k + 1)
  }

  return (
    <Card className="w-80 shrink-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">AMBER Jobs</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <FileSelector
          key={`prmtop-${selectorKey}`}
          experimentId={experimentId}
          ext={["prmtop", "parm7"]}
          title="Topology"
          onFileSelected={setPrmtopFile}
          ignoreFiles={jobs}
        />
        <FileSelector
          key={`inpcrd-${selectorKey}`}
          experimentId={experimentId}
          ext={["inpcrd", "rst7", "nc"]}
          title="Coordinates"
          onFileSelected={setInpcrdFile}
        />
        <FileSelector
          key={`mdin-${selectorKey}`}
          experimentId={experimentId}
          ext={["mdin", "in"]}
          title="Run Control"
          onFileSelected={setMdinFile}
        />
        <Button variant="default" disabled={!canAdd} onClick={handleAdd}>
          <Plus className="mr-1 h-4 w-4" />
          Add AMBER Job
        </Button>

        <JobSelectorList
          files={jobs}
          selectedFile={selectedPrmtop}
          loading={loading}
          onSelect={onSelectJob}
          onDelete={onDeleteJob}
        />
      </CardContent>
    </Card>
  )
}

export default AmberSelector
