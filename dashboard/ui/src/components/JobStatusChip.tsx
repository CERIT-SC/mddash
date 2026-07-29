import { Loader2 } from "lucide-react"

import { isActiveJobStatus, jobStatusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import type { JobStatus } from "@/util/types"
import { Badge } from "@/components/ui/badge"

type JobStatusChipProps = {
  status: JobStatus
  className?: string
}

export function JobStatusChip({ status, className }: JobStatusChipProps) {
  return (
    <Badge variant="outline" className={cn("text-xs", jobStatusBadgeClass(status), className)}>
      {isActiveJobStatus(status) && <Loader2 className="animate-spin" />}
      {status}
    </Badge>
  )
}
