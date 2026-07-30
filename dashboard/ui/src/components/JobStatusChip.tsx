import { isActiveJobStatus, jobStatusBadgeClass } from "@/lib/status"
import type { JobStatus } from "@/util/types"
import { StatusChip } from "@/components/StatusChip"

type JobStatusChipProps = {
  status: JobStatus
  className?: string
}

export function JobStatusChip({ status, className }: JobStatusChipProps) {
  return (
    <StatusChip
      label={status}
      active={isActiveJobStatus(status)}
      statusClassName={jobStatusBadgeClass(status)}
      className={className}
    />
  )
}
