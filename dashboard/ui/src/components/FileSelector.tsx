import { useEffect, useMemo, useState } from "react"

import { SELECT_NONE } from "@/util/const"
import { formatFileSize } from "@/util/helpers"
import { useFiles } from "@/hooks/use-files"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export interface FileSelectorProps {
  experimentId: string
  ext: string | string[]
  title: string
  onFileSelected: (filePath: string) => void
  className?: string
  ignoreFiles?: string[]
}

const FileSelector = (props: FileSelectorProps) => {
  const { experimentId, ext, onFileSelected, title, className, ignoreFiles = [] } = props
  const { data: availableFiles = [] } = useFiles(experimentId, ext)
  const [selectedFile, setSelectedFile] = useState<string>("")

  const filteredFiles = useMemo(
    () => availableFiles.filter((file) => !ignoreFiles.includes(file.name)),
    [availableFiles, ignoreFiles]
  )

  useEffect(() => {
    if (selectedFile && !filteredFiles.some((file) => file.url === selectedFile)) {
      setSelectedFile("")
      onFileSelected("")
    }
  }, [filteredFiles, selectedFile, onFileSelected])

  const handleChange = (value: string) => {
    const url = value === SELECT_NONE ? "" : value
    setSelectedFile(url)
    onFileSelected(url)
  }

  const id = `file-selector-${title.toLowerCase().replace(/\s+/g, "-")}`

  return (
    <div className={className}>
      <Label htmlFor={id} className="mb-1 block text-sm font-medium">
        {title}
      </Label>
      <Select value={selectedFile || SELECT_NONE} onValueChange={handleChange}>
        <SelectTrigger id={id}>
          <SelectValue placeholder={title} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SELECT_NONE}>
            <em>None</em>
          </SelectItem>
          {filteredFiles.map((file) => (
            <SelectItem key={file.name} value={file.url}>
              {file.name} ({formatFileSize(file.size)})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default FileSelector
