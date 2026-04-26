import { Loader2, Trash2 } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface JobSelectorListProps {
  files: string[]
  selectedFile: string | null
  loading?: boolean
  onSelect: (file: string | null) => void
  onDelete: (file: string) => void
}

const JobSelectorList = ({ files, selectedFile, loading, onSelect, onDelete }: JobSelectorListProps) => {
  if (loading) {
    return (
      <div className="flex justify-center py-2">
        <Loader2 className="text-muted-foreground h-5 w-5 animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {files.map((file) => (
        <div
          key={file}
          className={cn(
            "flex cursor-pointer items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
            selectedFile === file
              ? "border-foreground bg-primary text-primary-foreground"
              : "border-border hover:bg-muted"
          )}
          onClick={() => onSelect(selectedFile === file ? null : file)}
        >
          <span className="flex min-w-0 flex-1 flex-col">
            {file.includes("/") && (
              <span
                className={cn(
                  "truncate text-xs",
                  selectedFile === file ? "text-primary-foreground/70" : "text-muted-foreground"
                )}
              >
                {file.slice(0, file.lastIndexOf("/"))}/
              </span>
            )}
            <span className={cn("overflow-hidden text-ellipsis whitespace-nowrap", file.includes("/") && "pl-2")}>
              {file.split("/").pop()}
            </span>
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="delete"
            className={cn(
              "h-6 w-6 shrink-0",
              selectedFile === file ? "text-primary-foreground hover:bg-primary-foreground/20" : ""
            )}
            onClick={(e) => {
              e.stopPropagation()
              onDelete(file)
            }}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ))}
    </div>
  )
}

export default JobSelectorList
