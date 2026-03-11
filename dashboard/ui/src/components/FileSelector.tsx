import { useEffect, useMemo, useState } from "react"

import { SELECT_NONE } from "@/util/const"
import { formatFileSize } from "@/util/helpers"
import type { FileOption } from "@/util/types"
import { useFiles } from "@/hooks/use-files"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

function FileLabel({ file }: { file: FileOption }) {
  const dir = file.path.includes("/") ? file.path.slice(0, file.path.lastIndexOf("/")) : null
  return (
    <span className="flex min-w-0 flex-col overflow-hidden">
      {dir && <span className="text-muted-foreground truncate text-xs">{dir}/</span>}
      <span className={dir ? "truncate pl-2" : "truncate"}>
        {file.name} ({formatFileSize(file.size)})
      </span>
    </span>
  )
}

export interface FileSelectorProps {
  experimentId: string
  ext: string | string[]
  title: string
  onFileSelected: (file: FileOption | null) => void
  className?: string
  ignoreFiles?: string[]
}

const FileSelector = (props: FileSelectorProps) => {
  const { experimentId, ext, onFileSelected, title, className, ignoreFiles = [] } = props
  const { data: availableFiles = [] } = useFiles(experimentId, ext)
  const [selectedFile, setSelectedFile] = useState<string>("")

  const filteredFiles = useMemo(
    () => availableFiles.filter((file) => !ignoreFiles.includes(file.path)),
    [availableFiles, ignoreFiles]
  )

  useEffect(() => {
    if (selectedFile && !filteredFiles.some((file) => file.url === selectedFile)) {
      setSelectedFile("")
      onFileSelected(null)
    }
  }, [filteredFiles, selectedFile, onFileSelected])

  const handleChange = (value: string) => {
    if (value === SELECT_NONE) {
      setSelectedFile("")
      onFileSelected(null)
      return
    }
    setSelectedFile(value)
    const file = availableFiles.find((f) => f.url === value)
    onFileSelected(file ?? null)
  }

  const id = `file-selector-${title.toLowerCase().replace(/\s+/g, "-")}`

  return (
    <div className={className}>
      <Label htmlFor={id} className="mb-1 block text-sm font-medium">
        {title}
      </Label>
      <Select value={selectedFile || SELECT_NONE} onValueChange={handleChange}>
        <SelectTrigger
          id={id}
          className="h-auto overflow-hidden text-left *:data-[slot=select-value]:min-w-0 *:data-[slot=select-value]:overflow-hidden *:data-[slot=select-value]:line-clamp-none *:data-[slot=select-value]:items-start!"
        >
          <SelectValue placeholder={title} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SELECT_NONE}>
            <em>None</em>
          </SelectItem>
          {filteredFiles.map((file) => (
            <SelectItem key={file.path} value={file.url}>
              <FileLabel file={file} />
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default FileSelector
